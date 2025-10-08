"""
Unit tests for simkl_api module improvements.
Tests the enhanced error handling, retry logic, and rate limiting.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os

# Mock dependencies before importing
sys.modules['simkl_mps'] = MagicMock(__version__='test')
sys.modules['simkl_mps.credentials'] = MagicMock()

# Add parent directory to path  
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import the actual module
from simkl_mps import simkl_api
import requests


class TestMakeApiRequest:
    """Tests for the _make_api_request helper function"""
    
    def test_successful_get_request(self):
        """Test successful GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            response = simkl_api._make_api_request(
                'get', 
                'https://api.simkl.com/test',
                headers={'test': 'header'}
            )
            
            assert response is not None
            assert response.status_code == 200
            mock_get.assert_called_once()
    
    def test_successful_post_request(self):
        """Test successful POST request"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"result": "created"}
        
        with patch('requests.post', return_value=mock_response) as mock_post:
            response = simkl_api._make_api_request(
                'post',
                'https://api.simkl.com/test',
                headers={'test': 'header'},
                json={'data': 'test'}
            )
            
            assert response is not None
            assert response.status_code == 201
            mock_post.assert_called_once()
    
    def test_rate_limiting_retry(self):
        """Test that rate limiting (HTTP 429) triggers retry"""
        # First call returns 429, second call succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {'Retry-After': '1'}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"result": "success"}
        
        with patch('requests.get', side_effect=[mock_response_429, mock_response_200]):
            with patch('time.sleep'):  # Mock sleep to speed up test
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_server_error_retry(self):
        """Test that server errors (5xx) trigger retry"""
        # First call returns 500, second call succeeds
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        
        with patch('requests.get', side_effect=[mock_response_500, mock_response_200]):
            with patch('time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_timeout_retry(self):
        """Test that timeouts trigger retry"""
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        
        with patch('requests.get', side_effect=[requests.exceptions.Timeout(), mock_response_ok]):
            with patch('time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_connection_error_retry(self):
        """Test that connection errors trigger retry"""
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        
        with patch('requests.get', side_effect=[requests.exceptions.ConnectionError(), mock_response_ok]):
            with patch('time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_max_retries_exceeded(self):
        """Test that max retries returns None when exceeded"""
        with patch('requests.get', side_effect=requests.exceptions.Timeout()):
            with patch('time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'},
                    max_retries=2
                )
                
                assert response is None
    
    def test_client_error_no_retry(self):
        """Test that client errors (4xx except 429) don't trigger retry"""
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        with patch('requests.get', return_value=mock_response_404) as mock_get:
            response = simkl_api._make_api_request(
                'get',
                'https://api.simkl.com/test',
                headers={'test': 'header'}
            )
            
            assert response is not None
            assert response.status_code == 404
            # Should only be called once (no retry)
            assert mock_get.call_count == 1


class TestNormalizeSimklIds:
    """Tests for the _normalize_simkl_ids function"""
    
    def test_normalize_simkl_id_to_simkl(self):
        """Test that simkl_id is normalized to simkl"""
        item = {
            'ids': {
                'simkl_id': 12345
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is True
        assert item['ids']['simkl'] == 12345
        assert item['ids']['simkl_id'] == 12345  # Original should remain
    
    def test_already_has_simkl_key(self):
        """Test that items with simkl key are not modified"""
        item = {
            'ids': {
                'simkl': 12345
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is True
        assert item['ids']['simkl'] == 12345
    
    def test_missing_ids_field(self):
        """Test that items without ids field return False"""
        item = {
            'title': 'Test'
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is False
    
    def test_no_valid_id(self):
        """Test that items without valid IDs return False"""
        item = {
            'ids': {
                'imdb': 'tt1234567'
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestMakeApiRequest:
    """Tests for the _make_api_request helper function"""
    
    def test_successful_get_request(self):
        """Test successful GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        
        with patch('simkl_mps.simkl_api.requests.get', return_value=mock_response) as mock_get:
            response = simkl_api._make_api_request(
                'get', 
                'https://api.simkl.com/test',
                headers={'test': 'header'}
            )
            
            assert response is not None
            assert response.status_code == 200
            mock_get.assert_called_once()
    
    def test_successful_post_request(self):
        """Test successful POST request"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"result": "created"}
        
        with patch('simkl_mps.simkl_api.requests.post', return_value=mock_response) as mock_post:
            response = simkl_api._make_api_request(
                'post',
                'https://api.simkl.com/test',
                headers={'test': 'header'},
                json={'data': 'test'}
            )
            
            assert response is not None
            assert response.status_code == 201
            mock_post.assert_called_once()
    
    def test_rate_limiting_retry(self):
        """Test that rate limiting (HTTP 429) triggers retry"""
        # First call returns 429, second call succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {'Retry-After': '1'}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"result": "success"}
        
        with patch('simkl_mps.simkl_api.requests.get', side_effect=[mock_response_429, mock_response_200]):
            with patch('simkl_mps.simkl_api.time.sleep'):  # Mock sleep to speed up test
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_server_error_retry(self):
        """Test that server errors (5xx) trigger retry"""
        # First call returns 500, second call succeeds
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        
        with patch('simkl_mps.simkl_api.requests.get', side_effect=[mock_response_500, mock_response_200]):
            with patch('simkl_mps.simkl_api.time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_timeout_retry(self):
        """Test that timeouts trigger retry"""
        from requests.exceptions import Timeout
        
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        
        with patch('simkl_mps.simkl_api.requests.get', side_effect=[Timeout(), mock_response_ok]):
            with patch('simkl_mps.simkl_api.time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_connection_error_retry(self):
        """Test that connection errors trigger retry"""
        from requests.exceptions import ConnectionError
        
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        
        with patch('simkl_mps.simkl_api.requests.get', side_effect=[ConnectionError(), mock_response_ok]):
            with patch('simkl_mps.simkl_api.time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'}
                )
                
                assert response is not None
                assert response.status_code == 200
    
    def test_max_retries_exceeded(self):
        """Test that max retries returns None when exceeded"""
        from requests.exceptions import Timeout
        
        with patch('simkl_mps.simkl_api.requests.get', side_effect=Timeout()):
            with patch('simkl_mps.simkl_api.time.sleep'):  # Mock sleep
                response = simkl_api._make_api_request(
                    'get',
                    'https://api.simkl.com/test',
                    headers={'test': 'header'},
                    max_retries=2
                )
                
                assert response is None
    
    def test_client_error_no_retry(self):
        """Test that client errors (4xx except 429) don't trigger retry"""
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        with patch('simkl_mps.simkl_api.requests.get', return_value=mock_response_404) as mock_get:
            response = simkl_api._make_api_request(
                'get',
                'https://api.simkl.com/test',
                headers={'test': 'header'}
            )
            
            assert response is not None
            assert response.status_code == 404
            # Should only be called once (no retry)
            assert mock_get.call_count == 1


class TestNormalizeSimklIds:
    """Tests for the _normalize_simkl_ids function"""
    
    def test_normalize_simkl_id_to_simkl(self):
        """Test that simkl_id is normalized to simkl"""
        item = {
            'ids': {
                'simkl_id': 12345
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is True
        assert item['ids']['simkl'] == 12345
        assert item['ids']['simkl_id'] == 12345  # Original should remain
    
    def test_already_has_simkl_key(self):
        """Test that items with simkl key are not modified"""
        item = {
            'ids': {
                'simkl': 12345
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is True
        assert item['ids']['simkl'] == 12345
    
    def test_missing_ids_field(self):
        """Test that items without ids field return False"""
        item = {
            'title': 'Test'
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is False
    
    def test_no_valid_id(self):
        """Test that items without valid IDs return False"""
        item = {
            'ids': {
                'imdb': 'tt1234567'
            }
        }
        
        result = simkl_api._normalize_simkl_ids(item, "test_item", "Test Title")
        
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
