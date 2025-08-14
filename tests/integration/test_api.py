import pytest

class TestEnhancedAPI:
    
    def test_discord_webhook(self, client, auth_headers):
        """Test Discord webhook endpoint"""
        payload = {
            "note": "Test note from Discord",
            "tags": "discord,test",
            "type": "discord"
        }
        
        response = client.post("/webhook/discord", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert "note_id" in response.json()
    
    def test_enhanced_search(self, client, auth_headers):
        """Test enhanced search endpoint"""
        # Create a note first
        client.post("/capture", data={"note": "test note", "tags": "test"}, headers=auth_headers)
        
        # Search for it
        payload = {"query": "test", "limit": 10}
        response = client.post("/api/search/enhanced", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
