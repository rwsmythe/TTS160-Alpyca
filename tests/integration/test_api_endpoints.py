"""
Integration tests for Alpaca API endpoints.

Tests the telescope.py responders with mocked device and cache,
verifying proper Alpaca protocol compliance.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from falcon import testing

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestAlpacaAPISetup:
    """Test API setup and basic responses."""

    @pytest.fixture
    def mock_device(self):
        """Create a mock TTS160Device."""
        device = MagicMock()
        device.Connected = True
        device.RightAscension = 12.5
        device.Declination = 45.0
        device.Altitude = 60.0
        device.Azimuth = 180.0
        device.Slewing = False
        device.Tracking = True
        device.AtPark = False
        device.AtHome = False
        device.IsPulseGuiding = False
        device.SideOfPier = 0
        device.SiderealTime = 12.0
        device.AlignmentMode = 2  # German Polar
        device.SupportedActions = []
        return device

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache."""
        cache = MagicMock()
        cache.get_property.return_value = None  # Force fresh reads by default
        return cache

    @pytest.fixture
    def api_client(self, mock_device, mock_cache, mock_logger):
        """Create Falcon test client with mocked dependencies."""
        import telescope
        import shr
        import exceptions
        from falcon import App

        # Set up module globals
        telescope.TTS160_dev = mock_device
        telescope.TTS160_cache = mock_cache
        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        # Create minimal Falcon app with a few endpoints
        # Use {devnum:int} template to match PreProcessRequest expectations
        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/name', telescope.name())
        app.add_route('/api/v1/telescope/{devnum:int}/connected', telescope.connected())
        app.add_route('/api/v1/telescope/{devnum:int}/rightascension', telescope.rightascension())
        app.add_route('/api/v1/telescope/{devnum:int}/declination', telescope.declination())
        app.add_route('/api/v1/telescope/{devnum:int}/altitude', telescope.altitude())
        app.add_route('/api/v1/telescope/{devnum:int}/azimuth', telescope.azimuth())
        app.add_route('/api/v1/telescope/{devnum:int}/slewing', telescope.slewing())
        app.add_route('/api/v1/telescope/{devnum:int}/tracking', telescope.tracking())
        app.add_route('/api/v1/telescope/{devnum:int}/athome', telescope.athome())
        app.add_route('/api/v1/telescope/{devnum:int}/atpark', telescope.atpark())
        app.add_route('/api/v1/telescope/{devnum:int}/alignmentmode', telescope.alignmentmode())
        app.add_route('/api/v1/telescope/{devnum:int}/interfaceversion', telescope.interfaceversion())

        return testing.TestClient(app)


class TestMetadataEndpoints:
    """Test metadata and info endpoints."""

    @pytest.fixture
    def client(self, mock_logger):
        """Create test client for metadata endpoints."""
        import telescope
        import shr
        import exceptions
        from falcon import App, testing

        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/name', telescope.name())
        app.add_route('/api/v1/telescope/{devnum:int}/interfaceversion', telescope.interfaceversion())
        app.add_route('/api/v1/telescope/{devnum:int}/driverversion', telescope.driverversion())
        app.add_route('/api/v1/telescope/{devnum:int}/driverinfo', telescope.driverinfo())

        return testing.TestClient(app)

    @pytest.mark.integration
    def test_name_returns_device_name(self, client):
        """GET /name should return device name."""
        response = client.simulate_get(
            '/api/v1/telescope/0/name',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] == 'TTS160'

    @pytest.mark.integration
    def test_interfaceversion_returns_v4(self, client):
        """GET /interfaceversion should return 4 for ITelescopeV4."""
        response = client.simulate_get(
            '/api/v1/telescope/0/interfaceversion',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] == 4

    @pytest.mark.integration
    def test_response_includes_transaction_ids(self, client):
        """Response should include transaction IDs."""
        response = client.simulate_get(
            '/api/v1/telescope/0/name',
            params={'ClientID': '42', 'ClientTransactionID': '123'}
        )

        data = json.loads(response.text)
        assert data['ClientTransactionID'] == 123
        assert 'ServerTransactionID' in data
        assert data['ServerTransactionID'] > 0


class TestPropertyEndpoints(TestAlpacaAPISetup):
    """Test property GET endpoints."""

    @pytest.mark.integration
    def test_rightascension_returns_value(self, api_client, mock_device):
        """GET /rightascension should return RA value."""
        mock_device.RightAscension = 15.75

        response = api_client.simulate_get(
            '/api/v1/telescope/0/rightascension',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 15.75) < 0.0001

    @pytest.mark.integration
    def test_declination_returns_value(self, api_client, mock_device):
        """GET /declination should return Dec value."""
        mock_device.Declination = -30.5

        response = api_client.simulate_get(
            '/api/v1/telescope/0/declination',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - (-30.5)) < 0.0001

    @pytest.mark.integration
    def test_altitude_returns_value(self, api_client, mock_device):
        """GET /altitude should return altitude value."""
        mock_device.Altitude = 45.0

        response = api_client.simulate_get(
            '/api/v1/telescope/0/altitude',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 45.0) < 0.0001

    @pytest.mark.integration
    def test_azimuth_returns_value(self, api_client, mock_device):
        """GET /azimuth should return azimuth value."""
        mock_device.Azimuth = 270.0

        response = api_client.simulate_get(
            '/api/v1/telescope/0/azimuth',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 270.0) < 0.0001

    @pytest.mark.integration
    def test_slewing_returns_boolean(self, api_client, mock_device):
        """GET /slewing should return boolean value."""
        mock_device.Slewing = True

        response = api_client.simulate_get(
            '/api/v1/telescope/0/slewing',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] is True

    @pytest.mark.integration
    def test_tracking_returns_boolean(self, api_client, mock_device):
        """GET /tracking should return boolean value."""
        mock_device.Tracking = False

        response = api_client.simulate_get(
            '/api/v1/telescope/0/tracking',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] is False


class TestNotConnectedError(TestAlpacaAPISetup):
    """Test NotConnectedException handling."""

    @pytest.mark.integration
    def test_rightascension_not_connected(self, api_client, mock_device):
        """GET /rightascension should return error when not connected."""
        mock_device.Connected = False

        response = api_client.simulate_get(
            '/api/v1/telescope/0/rightascension',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] != 0  # NotConnectedException

    @pytest.mark.integration
    def test_altitude_not_connected(self, api_client, mock_device):
        """GET /altitude should return error when not connected."""
        mock_device.Connected = False

        response = api_client.simulate_get(
            '/api/v1/telescope/0/altitude',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] != 0

    @pytest.mark.integration
    def test_slewing_not_connected(self, api_client, mock_device):
        """GET /slewing should return error when not connected."""
        mock_device.Connected = False

        response = api_client.simulate_get(
            '/api/v1/telescope/0/slewing',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] != 0


class TestCacheIntegration(TestAlpacaAPISetup):
    """Test cache integration with API endpoints."""

    @pytest.mark.integration
    def test_cache_hit_returns_cached_value(self, api_client, mock_device, mock_cache):
        """When cache has fresh value, should return it without device access."""
        import time

        # Setup cache to return fresh value
        mock_cache.get_property.return_value = {
            'value': 99.99,
            'timestamp': time.time(),  # Very fresh
            'error': None
        }
        mock_device.Altitude = 50.0  # Device has different value

        response = api_client.simulate_get(
            '/api/v1/telescope/0/altitude',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 99.99) < 0.0001  # Should be cached value

    @pytest.mark.integration
    def test_cache_miss_reads_from_device(self, api_client, mock_device, mock_cache):
        """When cache is empty, should read from device."""
        mock_cache.get_property.return_value = None
        mock_device.Altitude = 55.0

        response = api_client.simulate_get(
            '/api/v1/telescope/0/altitude',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 55.0) < 0.0001  # Should be device value

    @pytest.mark.integration
    def test_stale_cache_reads_from_device(self, api_client, mock_device, mock_cache):
        """When cache is stale, should read from device."""
        import time

        # Setup stale cache entry (10 seconds old, threshold is 0.5s for altitude)
        mock_cache.get_property.return_value = {
            'value': 99.99,
            'timestamp': time.time() - 10,  # Old entry
            'error': None
        }
        mock_device.Altitude = 60.0

        response = api_client.simulate_get(
            '/api/v1/telescope/0/altitude',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert abs(data['Value'] - 60.0) < 0.0001  # Should be fresh device value


class TestBadRequests:
    """Test handling of malformed requests."""

    @pytest.fixture
    def client(self, mock_logger):
        """Create test client."""
        import telescope
        import shr
        import exceptions
        from falcon import App, testing

        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger
        telescope.TTS160_dev = MagicMock()
        telescope.TTS160_dev.Connected = True

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/name', telescope.name())

        return testing.TestClient(app)

    @pytest.mark.integration
    def test_missing_clientid_uses_default(self, client):
        """Missing ClientID should default to 0."""
        response = client.simulate_get(
            '/api/v1/telescope/0/name',
            params={'ClientTransactionID': '1'}
        )

        # Should still work with default
        assert response.status == '200 OK'

    @pytest.mark.integration
    def test_invalid_clientid_returns_error(self, client):
        """Invalid ClientID should return 400."""
        response = client.simulate_get(
            '/api/v1/telescope/0/name',
            params={'ClientID': 'invalid', 'ClientTransactionID': '1'}
        )

        assert response.status == '400 Bad Request'

    @pytest.mark.integration
    def test_negative_clientid_returns_error(self, client):
        """Negative ClientID should return 400."""
        response = client.simulate_get(
            '/api/v1/telescope/0/name',
            params={'ClientID': '-1', 'ClientTransactionID': '1'}
        )

        assert response.status == '400 Bad Request'


class TestAlignmentMode(TestAlpacaAPISetup):
    """Test alignment mode endpoint."""

    @pytest.mark.integration
    def test_alignmentmode_returns_germanpolar(self, api_client, mock_device):
        """GET /alignmentmode should return alignment mode."""
        mock_device.AlignmentMode = 2  # German Polar

        response = api_client.simulate_get(
            '/api/v1/telescope/0/alignmentmode',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] == 2


class TestParkHomeStatus(TestAlpacaAPISetup):
    """Test park and home status endpoints."""

    @pytest.mark.integration
    def test_atpark_returns_true(self, api_client, mock_device):
        """GET /atpark should return park status."""
        mock_device.AtPark = True

        response = api_client.simulate_get(
            '/api/v1/telescope/0/atpark',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] is True

    @pytest.mark.integration
    def test_athome_returns_false(self, api_client, mock_device):
        """GET /athome should return home status."""
        mock_device.AtHome = False

        response = api_client.simulate_get(
            '/api/v1/telescope/0/athome',
            params={'ClientID': '1', 'ClientTransactionID': '1'}
        )

        assert response.status == '200 OK'
        data = json.loads(response.text)
        assert data['ErrorNumber'] == 0
        assert data['Value'] is False
