#!/usr/bin/env python3
"""
Note Relationships and Cross-Note Discovery for Second Brain
Implements semantic similarity clustering and related note discovery
"""

import sqlite3
import numpy as np
import pickle
from typing import List, Dict
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import time
import json

try:
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.cluster import DBSCAN
    import networkx as nx
    CLUSTERING_AVAILABLE = True
except ImportError:
    CLUSTERING_AVAILABLE = False
    print("⚠️  Clustering dependencies not available. Install: pip install scikit-learn networkx")

logger = logging.getLogger(__name__)

@dataclass
class RelatedNote:
    """Represents a note related to another note"""
    note_id: int
    title: str
    summary: str
    tags: List[str]
    similarity_score: float
    relationship_type: str  # 'semantic', 'tag_overlap', 'content_reference'
    snippet: str
    timestamp: str

@dataclass
class NoteCluster:
    """Represents a cluster of semantically related notes"""
    cluster_id: int
    note_ids: List[int]
    cluster_theme: str
    representative_note_id: int
    avg_similarity: float
    created_at: str

class NoteRelationshipEngine:
    """Discovers and manages relationships between notes"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._semantic_search = None
        self._embedding_manager = None
        self._init_database()
    
    def _get_semantic_search(self):
        """Lazy load semantic search"""
        if self._semantic_search is None:
            try:
                from services.search_adapter import SearchService
                self._semantic_search = SearchService(self.db_path)
            except ImportError:
                logger.warning("Semantic search not available")
                return None
        return self._semantic_search
    
    def _get_embedding_manager(self):
        """Lazy load embedding manager"""
        if self._embedding_manager is None:
            try:
                from embedding_manager import EmbeddingManager
                self._embedding_manager = EmbeddingManager(self.db_path)
            except ImportError:
                logger.warning("Embedding manager not available")
                return None
        return self._embedding_manager
    
    def _init_database(self):
        """Initialize database tables for note relationships"""
        conn = sqlite3.connect(self.db_path)
        
        # Note relationships table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS note_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_note_id INTEGER NOT NULL,
                target_note_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,
                similarity_score REAL NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_note_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY(target_note_id) REFERENCES notes(id) ON DELETE CASCADE,
                UNIQUE(source_note_id, target_note_id, relationship_type)
            )
        """)
        
        # Note clusters table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS note_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_theme TEXT NOT NULL,
                representative_note_id INTEGER,
                avg_similarity REAL,
                note_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(representative_note_id) REFERENCES notes(id)
            )
        """)
        
        # Cluster membership table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cluster_membership (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                note_id INTEGER NOT NULL,
                membership_strength REAL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(cluster_id) REFERENCES note_clusters(id) ON DELETE CASCADE,
                FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
                UNIQUE(cluster_id, note_id)
            )
        """)
        
        # Create indexes for performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_source ON note_relationships(source_note_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_target ON note_relationships(target_note_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relationships_score ON note_relationships(similarity_score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cluster_membership_note ON cluster_membership(note_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cluster_membership_cluster ON cluster_membership(cluster_id)")
        
        conn.commit()
        conn.close()
    
    def find_similar_notes(self, note_id: int, user_id: int, 
                          limit: int = 10, 
                          min_similarity: float = 0.3,
                          include_types: List[str] = None) -> List[RelatedNote]:
        """Find notes similar to the given note"""
        
        # Get embeddings for comparison
        embedding_manager = self._get_embedding_manager()
        if not embedding_manager:
            return self._fallback_similarity_search(note_id, user_id, limit)
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get the source note embedding
            source_embedding = embedding_manager.get_embedding(note_id)
            if source_embedding is None:
                logger.warning(f"No embedding found for note {note_id}")
                return []
            
            # Get all embeddings for user's notes
            all_embeddings = embedding_manager.get_all_embeddings()
            if not all_embeddings:
                return []
            
            # Get user's note IDs for filtering
            user_note_ids = {row[0] for row in conn.execute("""
                SELECT id FROM notes WHERE user_id = ? AND id != ?
            """, (user_id, note_id)).fetchall()}
            
            # Filter embeddings to user's notes only
            user_embeddings = [(nid, emb) for nid, emb in all_embeddings 
                              if nid in user_note_ids]
            
            if not user_embeddings:
                return []
            
            # Calculate similarities
            similarities = []
            for target_note_id, target_embedding in user_embeddings:
                similarity = cosine_similarity(
                    source_embedding.reshape(1, -1),
                    target_embedding.reshape(1, -1)
                )[0][0]
                
                if similarity >= min_similarity:
                    similarities.append((target_note_id, float(similarity)))
            
            # Sort by similarity and limit
            similarities.sort(key=lambda x: x[1], reverse=True)
            similarities = similarities[:limit]
            
            # Get note details
            related_notes = []
            for target_note_id, similarity in similarities:
                note_data = conn.execute("""
                    SELECT title, summary, tags, content, timestamp, type
                    FROM notes WHERE id = ?
                """, (target_note_id,)).fetchone()
                
                if note_data:
                    # Apply type filter if specified
                    if include_types and note_data['type'] not in include_types:
                        continue
                    
                    # Generate snippet
                    snippet = self._generate_snippet(
                        note_data['content'] or note_data['summary'] or note_data['title'], 
                        150
                    )
                    
                    related_notes.append(RelatedNote(
                        note_id=target_note_id,
                        title=note_data['title'] or '',
                        summary=note_data['summary'] or '',
                        tags=note_data['tags'].split(',') if note_data['tags'] else [],
                        similarity_score=similarity,
                        relationship_type='semantic',
                        snippet=snippet,
                        timestamp=note_data['timestamp'] or ''
                    ))
            
            conn.close()
            
            # Store relationships in database for future reference
            self._store_relationships(note_id, related_notes)
            
            return related_notes
            
        except Exception as e:
            logger.error(f"Failed to find similar notes: {e}")
            return []
    
    def _fallback_similarity_search(self, note_id: int, user_id: int, 
                                   limit: int) -> List[RelatedNote]:
        """Fallback similarity search using tag and content overlap"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            # Get source note
            source_note = conn.execute("""
                SELECT title, tags, content, summary FROM notes WHERE id = ? AND user_id = ?
            """, (note_id, user_id)).fetchone()
            
            if not source_note:
                return []
            
            source_tags = set(source_note['tags'].split(',')) if source_note['tags'] else set()
            source_content = (source_note['content'] or '') + ' ' + (source_note['summary'] or '')
            source_words = set(source_content.lower().split())
            
            # Find similar notes based on tag and content overlap
            similar_notes = conn.execute("""
                SELECT id, title, tags, content, summary, timestamp, type
                FROM notes 
                WHERE user_id = ? AND id != ?
                ORDER BY timestamp DESC
            """, (user_id, note_id)).fetchall()
            
            related = []
            for note in similar_notes:
                note_tags = set(note['tags'].split(',')) if note['tags'] else set()
                note_content = (note['content'] or '') + ' ' + (note['summary'] or '')
                note_words = set(note_content.lower().split())
                
                # Calculate similarity score based on tag and content overlap
                tag_overlap = len(source_tags & note_tags) / max(len(source_tags | note_tags), 1)
                content_overlap = len(source_words & note_words) / max(len(source_words | note_words), 1)
                similarity = (tag_overlap * 0.6) + (content_overlap * 0.4)
                
                if similarity > 0.1:  # Lower threshold for fallback
                    snippet = self._generate_snippet(
                        note['content'] or note['summary'] or note['title'], 150
                    )
                    
                    related.append(RelatedNote(
                        note_id=note['id'],
                        title=note['title'] or '',
                        summary=note['summary'] or '',
                        tags=note_tags,
                        similarity_score=similarity,
                        relationship_type='tag_content_overlap',
                        snippet=snippet,
                        timestamp=note['timestamp'] or ''
                    ))
            
            # Sort by similarity and limit
            related.sort(key=lambda x: x.similarity_score, reverse=True)
            conn.close()
            
            return related[:limit]
            
        except Exception as e:
            logger.error(f"Fallback similarity search failed: {e}")
            return []
    
    def _generate_snippet(self, text: str, max_length: int = 150) -> str:
        """Generate a snippet from text"""
        if not text:
            return ""
        
        text = text.strip()
        if len(text) <= max_length:
            return text
        
        return text[:max_length].rsplit(' ', 1)[0] + "..."
    
    def _store_relationships(self, source_note_id: int, related_notes: List[RelatedNote]):
        """Store note relationships in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Clear existing relationships for this source note
            conn.execute("""
                DELETE FROM note_relationships 
                WHERE source_note_id = ? AND relationship_type = 'semantic'
            """, (source_note_id,))
            
            # Store new relationships
            for related in related_notes:
                metadata = json.dumps({
                    'snippet': related.snippet,
                    'common_tags': list(set(related.tags)) if related.tags else []
                })
                
                conn.execute("""
                    INSERT OR REPLACE INTO note_relationships 
                    (source_note_id, target_note_id, relationship_type, 
                     similarity_score, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (source_note_id, related.note_id, related.relationship_type,
                      related.similarity_score, metadata, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store relationships: {e}")
    
    def discover_note_clusters(self, user_id: int, min_cluster_size: int = 3,
                              similarity_threshold: float = 0.4) -> List[NoteCluster]:
        """Discover clusters of related notes using DBSCAN clustering"""
        if not CLUSTERING_AVAILABLE:
            logger.warning("Clustering not available - dependencies not installed")
            return []
        
        embedding_manager = self._get_embedding_manager()
        if not embedding_manager:
            return []
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get user's notes with embeddings
            note_data = conn.execute("""
                SELECT n.id, n.title, n.summary, n.tags, ne.embedding
                FROM notes n
                JOIN note_embeddings ne ON n.id = ne.note_id
                WHERE n.user_id = ?
                ORDER BY n.timestamp DESC
            """, (user_id,)).fetchall()
            
            if len(note_data) < min_cluster_size:
                logger.info(f"Not enough notes for clustering: {len(note_data)}")
                return []
            
            # Extract embeddings and note info
            embeddings = []
            notes_info = []
            
            for row in note_data:
                note_id, title, summary, tags, embedding_blob = row
                try:
                    embedding = pickle.loads(embedding_blob)
                    embeddings.append(embedding)
                    notes_info.append({
                        'id': note_id,
                        'title': title or '',
                        'summary': summary or '',
                        'tags': tags.split(',') if tags else []
                    })
                except Exception as e:
                    logger.warning(f"Failed to load embedding for note {note_id}: {e}")
                    continue
            
            if len(embeddings) < min_cluster_size:
                return []
            
            # Perform DBSCAN clustering
            embeddings_array = np.array(embeddings)
            
            # Convert similarity threshold to distance threshold for DBSCAN
            distance_threshold = 1 - similarity_threshold
            
            clustering = DBSCAN(
                eps=distance_threshold, 
                min_samples=min_cluster_size, 
                metric='cosine'
            ).fit(embeddings_array)
            
            # Process clusters
            clusters = []
            unique_labels = set(clustering.labels_)
            
            for label in unique_labels:
                if label == -1:  # Skip noise points
                    continue
                
                # Get notes in this cluster
                cluster_indices = np.where(clustering.labels_ == label)[0]
                cluster_note_ids = [notes_info[i]['id'] for i in cluster_indices]
                cluster_notes = [notes_info[i] for i in cluster_indices]
                
                if len(cluster_note_ids) < min_cluster_size:
                    continue
                
                # Calculate average similarity within cluster
                cluster_embeddings = embeddings_array[cluster_indices]
                avg_similarity = self._calculate_avg_cluster_similarity(cluster_embeddings)
                
                # Determine cluster theme based on common tags and titles
                cluster_theme = self._determine_cluster_theme(cluster_notes)
                
                # Choose representative note (most central)
                representative_idx = self._find_representative_note(cluster_embeddings, cluster_indices)
                representative_note_id = notes_info[representative_idx]['id']
                
                cluster = NoteCluster(
                    cluster_id=len(clusters),
                    note_ids=cluster_note_ids,
                    cluster_theme=cluster_theme,
                    representative_note_id=representative_note_id,
                    avg_similarity=avg_similarity,
                    created_at=datetime.now().isoformat()
                )
                
                clusters.append(cluster)
            
            # Store clusters in database
            self._store_clusters(user_id, clusters)
            
            conn.close()
            logger.info(f"Discovered {len(clusters)} note clusters for user {user_id}")
            
            return clusters
            
        except Exception as e:
            logger.error(f"Cluster discovery failed: {e}")
            return []
    
    def _calculate_avg_cluster_similarity(self, cluster_embeddings: np.ndarray) -> float:
        """Calculate average pairwise similarity within cluster"""
        if len(cluster_embeddings) < 2:
            return 1.0
        
        similarities = []
        for i in range(len(cluster_embeddings)):
            for j in range(i + 1, len(cluster_embeddings)):
                sim = cosine_similarity(
                    cluster_embeddings[i:i+1], 
                    cluster_embeddings[j:j+1]
                )[0][0]
                similarities.append(sim)
        
        return float(np.mean(similarities)) if similarities else 0.0
    
    def _determine_cluster_theme(self, cluster_notes: List[Dict]) -> str:
        """Determine the theme/topic of a cluster based on common elements"""
        # Collect all tags
        all_tags = []
        for note in cluster_notes:
            all_tags.extend(note['tags'])
        
        # Find most common tags
        tag_counts = {}
        for tag in all_tags:
            if tag.strip():
                tag_counts[tag.strip()] = tag_counts.get(tag.strip(), 0) + 1
        
        common_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        if common_tags:
            theme_parts = [tag[0] for tag in common_tags]
            return f"Notes about: {', '.join(theme_parts)}"
        
        # Fallback to generic theme
        return f"Related notes ({len(cluster_notes)} notes)"
    
    def _find_representative_note(self, cluster_embeddings: np.ndarray, 
                                 cluster_indices: np.ndarray) -> int:
        """Find the most central note in the cluster"""
        if len(cluster_embeddings) == 1:
            return cluster_indices[0]
        
        # Calculate centroid
        centroid = np.mean(cluster_embeddings, axis=0)
        
        # Find note closest to centroid
        distances = []
        for embedding in cluster_embeddings:
            distance = 1 - cosine_similarity(
                centroid.reshape(1, -1), 
                embedding.reshape(1, -1)
            )[0][0]
            distances.append(distance)
        
        closest_idx = np.argmin(distances)
        return cluster_indices[closest_idx]
    
    def _store_clusters(self, user_id: int, clusters: List[NoteCluster]):
        """Store discovered clusters in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Clear existing clusters for this user
            # (This is a simple approach - in production you might want more sophisticated cluster management)
            user_note_ids = [row[0] for row in conn.execute("""
                SELECT id FROM notes WHERE user_id = ?
            """, (user_id,)).fetchall()]
            
            if user_note_ids:
                placeholders = ','.join('?' * len(user_note_ids))
                conn.execute(f"""
                    DELETE FROM cluster_membership 
                    WHERE note_id IN ({placeholders})
                """, user_note_ids)
            
            # Store new clusters
            for cluster in clusters:
                # Insert cluster
                cursor = conn.execute("""
                    INSERT INTO note_clusters 
                    (cluster_theme, representative_note_id, avg_similarity, note_count)
                    VALUES (?, ?, ?, ?)
                """, (cluster.cluster_theme, cluster.representative_note_id, 
                      cluster.avg_similarity, len(cluster.note_ids)))
                
                cluster_id = cursor.lastrowid
                
                # Insert cluster membership
                for note_id in cluster.note_ids:
                    conn.execute("""
                        INSERT INTO cluster_membership (cluster_id, note_id)
                        VALUES (?, ?)
                    """, (cluster_id, note_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store clusters: {e}")
    
    def get_note_clusters(self, user_id: int) -> List[Dict]:
        """Get existing clusters for a user"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            clusters = conn.execute("""
                SELECT c.id, c.cluster_theme, c.representative_note_id, 
                       c.avg_similarity, c.note_count, c.created_at,
                       GROUP_CONCAT(cm.note_id) as note_ids
                FROM note_clusters c
                JOIN cluster_membership cm ON c.id = cm.cluster_id
                JOIN notes n ON cm.note_id = n.id
                WHERE n.user_id = ?
                GROUP BY c.id
                ORDER BY c.avg_similarity DESC
            """, (user_id,)).fetchall()
            
            result = []
            for cluster in clusters:
                note_ids = [int(nid) for nid in cluster['note_ids'].split(',')]
                
                result.append({
                    'cluster_id': cluster['id'],
                    'theme': cluster['cluster_theme'],
                    'representative_note_id': cluster['representative_note_id'],
                    'avg_similarity': cluster['avg_similarity'],
                    'note_count': cluster['note_count'],
                    'note_ids': note_ids,
                    'created_at': cluster['created_at']
                })
            
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"Failed to get note clusters: {e}")
            return []
    
    def get_relationship_stats(self, user_id: int) -> Dict:
        """Get statistics about note relationships"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Count relationships by type
            relationship_counts = dict(conn.execute("""
                SELECT nr.relationship_type, COUNT(*) 
                FROM note_relationships nr
                JOIN notes n ON nr.source_note_id = n.id
                WHERE n.user_id = ?
                GROUP BY nr.relationship_type
            """, (user_id,)).fetchall())
            
            # Count total notes with relationships
            notes_with_relationships = conn.execute("""
                SELECT COUNT(DISTINCT nr.source_note_id)
                FROM note_relationships nr
                JOIN notes n ON nr.source_note_id = n.id
                WHERE n.user_id = ?
            """, (user_id,)).fetchone()[0]
            
            # Count clusters
            cluster_count = conn.execute("""
                SELECT COUNT(DISTINCT c.id)
                FROM note_clusters c
                JOIN cluster_membership cm ON c.id = cm.cluster_id
                JOIN notes n ON cm.note_id = n.id
                WHERE n.user_id = ?
            """, (user_id,)).fetchone()[0]
            
            # Total notes
            total_notes = conn.execute("""
                SELECT COUNT(*) FROM notes WHERE user_id = ?
            """, (user_id,)).fetchone()[0]
            
            conn.close()
            
            return {
                'total_notes': total_notes,
                'notes_with_relationships': notes_with_relationships,
                'relationship_types': relationship_counts,
                'cluster_count': cluster_count,
                'relationship_coverage': round((notes_with_relationships / total_notes) * 100, 1) if total_notes > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get relationship stats: {e}")
            return {}


async def main():
    """CLI interface for note relationships"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Note Relationship Engine")
    parser.add_argument("--db", default="notes.db", help="Database path")
    parser.add_argument("--user-id", type=int, default=1, help="User ID")
    parser.add_argument("--note-id", type=int, help="Find similar notes to this note")
    parser.add_argument("--clusters", action="store_true", help="Discover note clusters")
    parser.add_argument("--stats", action="store_true", help="Show relationship statistics")
    parser.add_argument("--limit", type=int, default=10, help="Number of similar notes to find")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    engine = NoteRelationshipEngine(args.db)
    
    if args.stats:
        stats = engine.get_relationship_stats(args.user_id)
        print("\n📊 Note Relationship Statistics")
        print("=" * 40)
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    if args.note_id:
        print(f"\n🔍 Finding notes similar to note {args.note_id}...")
        similar = engine.find_similar_notes(args.note_id, args.user_id, args.limit)
        
        if similar:
            print(f"Found {len(similar)} similar notes:")
            for i, note in enumerate(similar, 1):
                print(f"\n{i}. {note.title}")
                print(f"   Similarity: {note.similarity_score:.3f}")
                print(f"   Type: {note.relationship_type}")
                if note.snippet:
                    print(f"   Preview: {note.snippet}")
        else:
            print("No similar notes found.")
    
    if args.clusters:
        print(f"\n🎯 Discovering note clusters for user {args.user_id}...")
        clusters = engine.discover_note_clusters(args.user_id)
        
        if clusters:
            print(f"Discovered {len(clusters)} clusters:")
            for i, cluster in enumerate(clusters, 1):
                print(f"\n{i}. {cluster.cluster_theme}")
                print(f"   Notes: {len(cluster.note_ids)}")
                print(f"   Avg Similarity: {cluster.avg_similarity:.3f}")
                print(f"   Representative: Note {cluster.representative_note_id}")
        else:
            print("No clusters discovered.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
