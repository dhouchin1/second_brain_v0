"""
Advanced Search Query Parser for Second Brain
Supports Boolean operators, field-specific search, date ranges, and more
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class SearchOperator(Enum):
    """Search operators"""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class SearchField(Enum):
    """Searchable fields"""
    TITLE = "title"
    CONTENT = "content"
    TAG = "tag"
    TYPE = "type"
    DATE = "date"
    CREATED = "created"
    UPDATED = "updated"
    AUTHOR = "author"
    STATUS = "status"
    SOURCE = "source"


@dataclass
class SearchTerm:
    """Individual search term"""
    field: Optional[SearchField] = None
    value: str = ""
    operator: SearchOperator = SearchOperator.AND
    is_negated: bool = False
    is_phrase: bool = False
    is_wildcard: bool = False


@dataclass
class DateRange:
    """Date range for filtering"""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    field: SearchField = SearchField.CREATED


@dataclass
class SearchQuery:
    """Parsed search query"""
    terms: List[SearchTerm] = field(default_factory=list)
    date_ranges: List[DateRange] = field(default_factory=list)
    filters: Dict[str, List[str]] = field(default_factory=dict)
    min_score: float = 0.0
    limit: int = 50
    offset: int = 0


class AdvancedSearchParser:
    """
    Advanced search query parser with support for:
    - Boolean operators: AND, OR, NOT
    - Field-specific search: title:python, tag:work, type:note
    - Date ranges: created:2024-01-01..2024-12-31, date:last-week
    - Quoted phrases: "machine learning"
    - Wildcards: pyth*
    - Negation: -tag:draft, NOT archived
    """

    # Regex patterns
    FIELD_SEARCH_PATTERN = r'(\w+):((?:"[^"]*")|(?:[^\s]+))'
    QUOTED_PHRASE_PATTERN = r'"([^"]*)"'
    DATE_RANGE_PATTERN = r'(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})'
    RELATIVE_DATE_PATTERN = r'(last|past|next)-(\d+)-(day|week|month|year)s?'
    BOOLEAN_PATTERN = r'\b(AND|OR|NOT)\b'

    # Date shortcuts
    DATE_SHORTCUTS = {
        'today': (0, 'day'),
        'yesterday': (-1, 'day'),
        'this-week': (0, 'week'),
        'last-week': (-1, 'week'),
        'this-month': (0, 'month'),
        'last-month': (-1, 'month'),
        'this-year': (0, 'year'),
        'last-year': (-1, 'year'),
    }

    def __init__(self):
        self.query = SearchQuery()

    def parse(self, query_string: str) -> SearchQuery:
        """
        Parse search query string into structured SearchQuery object
        """
        if not query_string or not query_string.strip():
            return self.query

        query_string = query_string.strip()
        self.query = SearchQuery()

        # Step 1: Extract field-specific searches
        query_string = self._extract_field_searches(query_string)

        # Step 2: Extract quoted phrases
        query_string = self._extract_phrases(query_string)

        # Step 3: Process boolean operators
        query_string = self._process_boolean_operators(query_string)

        # Step 4: Process remaining terms
        self._process_remaining_terms(query_string)

        return self.query

    def _extract_field_searches(self, query_string: str) -> str:
        """Extract and process field-specific searches"""
        matches = re.finditer(self.FIELD_SEARCH_PATTERN, query_string)

        for match in matches:
            field_name = match.group(1).lower()
            field_value = match.group(2).strip('"')

            # Check if field is negated
            is_negated = False
            if field_name.startswith('-'):
                is_negated = True
                field_name = field_name[1:]

            # Map field name to SearchField enum
            try:
                search_field = SearchField(field_name)
            except ValueError:
                # Unknown field, treat as regular term
                continue

            # Handle date fields
            if search_field in [SearchField.DATE, SearchField.CREATED, SearchField.UPDATED]:
                date_range = self._parse_date_value(field_value, search_field)
                if date_range:
                    self.query.date_ranges.append(date_range)
            else:
                # Add as search term
                term = SearchTerm(
                    field=search_field,
                    value=field_value,
                    is_negated=is_negated,
                    is_phrase=True if '"' in match.group(2) else False
                )
                self.query.terms.append(term)

                # Also add to filters for easy access
                filter_key = field_name
                if filter_key not in self.query.filters:
                    self.query.filters[filter_key] = []
                if not is_negated:
                    self.query.filters[filter_key].append(field_value)

            # Remove from query string
            query_string = query_string.replace(match.group(0), '', 1)

        return query_string

    def _extract_phrases(self, query_string: str) -> str:
        """Extract quoted phrases"""
        matches = re.finditer(self.QUOTED_PHRASE_PATTERN, query_string)

        for match in matches:
            phrase = match.group(1)
            if phrase:
                term = SearchTerm(
                    value=phrase,
                    is_phrase=True
                )
                self.query.terms.append(term)

                # Remove from query string
                query_string = query_string.replace(match.group(0), '', 1)

        return query_string

    def _process_boolean_operators(self, query_string: str) -> str:
        """Process boolean operators"""
        # Split by boolean operators
        parts = re.split(self.BOOLEAN_PATTERN, query_string)

        current_operator = SearchOperator.AND
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Check if this is an operator
            if part.upper() in ['AND', 'OR', 'NOT']:
                try:
                    current_operator = SearchOperator(part.upper())
                except ValueError:
                    pass
            else:
                # This is a term
                words = part.split()
                for word in words:
                    if word:
                        is_negated = word.startswith('-') or word.startswith('NOT')
                        if is_negated:
                            word = word.lstrip('-').lstrip('NOT').strip()

                        if word:
                            term = SearchTerm(
                                value=word,
                                operator=current_operator,
                                is_negated=is_negated,
                                is_wildcard='*' in word or '?' in word
                            )
                            self.query.terms.append(term)

        return ""

    def _process_remaining_terms(self, query_string: str):
        """Process any remaining terms"""
        words = query_string.split()
        for word in words:
            word = word.strip()
            if word and word.upper() not in ['AND', 'OR', 'NOT']:
                is_negated = word.startswith('-')
                if is_negated:
                    word = word[1:]

                if word:
                    term = SearchTerm(
                        value=word,
                        is_negated=is_negated,
                        is_wildcard='*' in word or '?' in word
                    )
                    self.query.terms.append(term)

    def _parse_date_value(self, value: str, field: SearchField) -> Optional[DateRange]:
        """Parse date value into DateRange"""
        # Check for date range (YYYY-MM-DD..YYYY-MM-DD)
        range_match = re.match(self.DATE_RANGE_PATTERN, value)
        if range_match:
            try:
                start = datetime.strptime(range_match.group(1), '%Y-%m-%d')
                end = datetime.strptime(range_match.group(2), '%Y-%m-%d')
                return DateRange(start=start, end=end, field=field)
            except ValueError:
                pass

        # Check for relative date (last-7-days, past-2-weeks, etc.)
        relative_match = re.match(self.RELATIVE_DATE_PATTERN, value)
        if relative_match:
            direction = relative_match.group(1)  # last, past, next
            amount = int(relative_match.group(2))
            unit = relative_match.group(3)  # day, week, month, year

            if direction in ['last', 'past']:
                amount = -amount

            date_range = self._calculate_relative_date(amount, unit)
            if date_range:
                date_range.field = field
                return date_range

        # Check for shortcut (today, yesterday, this-week, etc.)
        if value in self.DATE_SHORTCUTS:
            amount, unit = self.DATE_SHORTCUTS[value]
            date_range = self._calculate_relative_date(amount, unit)
            if date_range:
                date_range.field = field
                return date_range

        # Try to parse as single date
        try:
            single_date = datetime.strptime(value, '%Y-%m-%d')
            # Single date means "on this day"
            end_of_day = single_date.replace(hour=23, minute=59, second=59)
            return DateRange(start=single_date, end=end_of_day, field=field)
        except ValueError:
            pass

        return None

    def _calculate_relative_date(self, amount: int, unit: str) -> Optional[DateRange]:
        """Calculate relative date range"""
        now = datetime.now()
        start = None
        end = now

        if unit == 'day':
            if amount == 0:
                # Today
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start = now + timedelta(days=amount)

        elif unit == 'week':
            if amount == 0:
                # This week (Monday to Sunday)
                start = now - timedelta(days=now.weekday())
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start = now + timedelta(weeks=amount)

        elif unit == 'month':
            if amount == 0:
                # This month
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                # Approximate (30 days per month)
                start = now + timedelta(days=amount * 30)

        elif unit == 'year':
            if amount == 0:
                # This year
                start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                # Approximate (365 days per year)
                start = now + timedelta(days=amount * 365)

        if start:
            return DateRange(start=start, end=end)

        return None

    def to_sql_conditions(self) -> Tuple[str, Dict]:
        """
        Convert parsed query to SQL WHERE conditions
        Returns: (where_clause, parameters)
        """
        conditions = []
        parameters = {}
        param_counter = 0

        # Process search terms
        for term in self.query.terms:
            param_name = f"term_{param_counter}"
            param_counter += 1

            if term.field:
                # Field-specific search
                field_name = term.field.value
                if term.is_phrase:
                    condition = f"{field_name} LIKE :{param_name}"
                    parameters[param_name] = f"%{term.value}%"
                elif term.is_wildcard:
                    condition = f"{field_name} LIKE :{param_name}"
                    wildcard_value = term.value.replace('*', '%').replace('?', '_')
                    parameters[param_name] = wildcard_value
                else:
                    condition = f"{field_name} = :{param_name}"
                    parameters[param_name] = term.value

                if term.is_negated:
                    condition = f"NOT ({condition})"

                conditions.append(condition)
            else:
                # Full-text search
                condition = f"(title LIKE :{param_name} OR content LIKE :{param_name})"
                parameters[param_name] = f"%{term.value}%"

                if term.is_negated:
                    condition = f"NOT {condition}"

                conditions.append(condition)

        # Process date ranges
        for idx, date_range in enumerate(self.query.date_ranges):
            field_name = date_range.field.value
            if date_range.start:
                param_name = f"date_start_{idx}"
                conditions.append(f"{field_name} >= :{param_name}")
                parameters[param_name] = date_range.start.isoformat()
            if date_range.end:
                param_name = f"date_end_{idx}"
                conditions.append(f"{field_name} <= :{param_name}")
                parameters[param_name] = date_range.end.isoformat()

        # Combine conditions
        if conditions:
            where_clause = " AND ".join(conditions)
        else:
            where_clause = "1=1"  # Always true

        return where_clause, parameters

    def to_fts_query(self) -> str:
        """
        Convert parsed query to FTS5 query syntax
        """
        fts_terms = []

        for term in self.query.terms:
            if term.field and term.field == SearchField.CONTENT:
                # FTS5 specific
                if term.is_phrase:
                    fts_term = f'"{term.value}"'
                elif term.is_wildcard:
                    fts_term = term.value  # FTS5 supports * wildcards
                else:
                    fts_term = term.value

                if term.is_negated:
                    fts_term = f"NOT {fts_term}"

                fts_terms.append(fts_term)

        # Join with AND by default
        return " AND ".join(fts_terms) if fts_terms else "*"


# ============================================
# Usage Examples
# ============================================

def example_queries():
    """Example usage of the parser"""
    parser = AdvancedSearchParser()

    examples = [
        'python machine learning',
        'title:python tag:tutorial',
        '"deep learning" AND neural networks',
        'tag:work OR tag:personal NOT tag:draft',
        'created:2024-01-01..2024-12-31',
        'date:last-7-days',
        'title:"second brain" type:note',
        '-tag:archived updated:this-month',
    ]

    for query_str in examples:
        query = parser.parse(query_str)
        print(f"\nQuery: {query_str}")
        print(f"Terms: {len(query.terms)}")
        print(f"Date ranges: {len(query.date_ranges)}")
        print(f"Filters: {query.filters}")
        print(f"SQL: {parser.to_sql_conditions()[0]}")


if __name__ == "__main__":
    example_queries()
