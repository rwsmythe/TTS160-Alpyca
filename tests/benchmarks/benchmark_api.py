"""
API response latency benchmarks.

These benchmarks measure the time taken to process API requests
under various conditions. Requires a running server for live tests.

Run with: pytest tests/benchmarks/benchmark_api.py -v --benchmark-only
"""

import pytest
import time
import statistics
import json
from unittest.mock import Mock, MagicMock, patch
from falcon import testing

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestAPIResponseLatency:
    """Benchmark API response times with mocked device."""

    @pytest.fixture
    def mock_device(self):
        """Create mock device."""
        device = MagicMock()
        device.Connected = True
        device.RightAscension = 12.5
        device.Declination = 45.0
        device.Altitude = 60.0
        device.Azimuth = 180.0
        device.Slewing = False
        device.Tracking = True
        return device

    @pytest.fixture
    def api_client(self, mock_device, mock_logger):
        """Create test client with mocked dependencies."""
        import telescope
        import shr
        import exceptions
        from falcon import App

        telescope.TTS160_dev = mock_device
        telescope.TTS160_cache = None  # No cache for pure device timing
        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/rightascension', telescope.rightascension())
        app.add_route('/api/v1/telescope/{devnum:int}/declination', telescope.declination())
        app.add_route('/api/v1/telescope/{devnum:int}/altitude', telescope.altitude())
        app.add_route('/api/v1/telescope/{devnum:int}/name', telescope.name())

        return testing.TestClient(app)

    @pytest.mark.benchmark
    def test_metadata_endpoint_latency(self, api_client):
        """Benchmark metadata endpoint (no device access)."""
        times = []

        for i in range(100):
            start = time.perf_counter()
            response = api_client.simulate_get(
                '/api/v1/telescope/{devnum:int}/name',
                params={'ClientID': str(i), 'ClientTransactionID': str(i)}
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)  # Convert to ms

            assert response.status == '200 OK'

        avg = statistics.mean(times)
        p95 = sorted(times)[95]
        p99 = sorted(times)[99]

        print(f"\nMetadata endpoint latency:")
        print(f"  Average: {avg:.3f}ms")
        print(f"  P95: {p95:.3f}ms")
        print(f"  P99: {p99:.3f}ms")

        # Should be very fast since no device access
        assert avg < 10, f"Average latency {avg:.3f}ms exceeds 10ms target"

    @pytest.mark.benchmark
    def test_property_endpoint_latency(self, api_client):
        """Benchmark property endpoint (with mocked device access)."""
        times = []

        for i in range(100):
            start = time.perf_counter()
            response = api_client.simulate_get(
                '/api/v1/telescope/{devnum:int}/rightascension',
                params={'ClientID': str(i), 'ClientTransactionID': str(i)}
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)

            assert response.status == '200 OK'

        avg = statistics.mean(times)
        p95 = sorted(times)[95]

        print(f"\nProperty endpoint latency (mocked device):")
        print(f"  Average: {avg:.3f}ms")
        print(f"  P95: {p95:.3f}ms")

        # With mocked device, should be reasonably fast
        assert avg < 20, f"Average latency {avg:.3f}ms exceeds 20ms target"


class TestCachePerformance:
    """Benchmark cache hit vs miss performance."""

    @pytest.fixture
    def cache(self, mock_logger):
        """Create cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()

    @pytest.fixture
    def api_client_with_cache(self, cache, mock_logger):
        """Create test client with cache enabled."""
        import telescope
        import shr
        import exceptions
        from falcon import App

        mock_device = MagicMock()
        mock_device.Connected = True
        mock_device.Altitude = 60.0

        telescope.TTS160_dev = mock_device
        telescope.TTS160_cache = cache
        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/altitude', telescope.altitude())

        return testing.TestClient(app)

    @pytest.mark.benchmark
    def test_cache_hit_latency(self, api_client_with_cache, cache):
        """Benchmark latency with cache hit."""
        # Warm the cache
        cache.update_property('Altitude', 60.0)

        times = []
        for i in range(100):
            start = time.perf_counter()
            response = api_client_with_cache.simulate_get(
                '/api/v1/telescope/{devnum:int}/altitude',
                params={'ClientID': str(i), 'ClientTransactionID': str(i)}
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)

        avg = statistics.mean(times)
        print(f"\nCache hit latency: {avg:.3f}ms average")

        # Cache hits should be fast
        assert avg < 15, f"Cache hit latency {avg:.3f}ms exceeds 15ms target"

    @pytest.mark.benchmark
    def test_cache_update_throughput(self, cache):
        """Benchmark cache update throughput."""
        start = time.perf_counter()
        iterations = 10000

        for i in range(iterations):
            cache.update_property('RightAscension', float(i % 24))

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nCache update throughput: {ops_per_sec:.0f} ops/sec")

        # Should handle at least 10000 updates per second
        assert ops_per_sec > 10000, f"Cache throughput {ops_per_sec:.0f} below 10000 ops/sec"

    @pytest.mark.benchmark
    def test_cache_read_throughput(self, cache):
        """Benchmark cache read throughput."""
        cache.update_property('Declination', 45.0)

        start = time.perf_counter()
        iterations = 10000

        for _ in range(iterations):
            cache.get_property_value('Declination')

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nCache read throughput: {ops_per_sec:.0f} ops/sec")

        # Reads should be even faster than writes
        assert ops_per_sec > 50000, f"Cache read throughput {ops_per_sec:.0f} below 50000 ops/sec"


class TestPriorityQueuePerformance:
    """Benchmark priority queue operations."""

    @pytest.mark.benchmark
    def test_priority_queue_ordering(self, mock_logger):
        """Benchmark priority queue insertion and extraction."""
        from tts160_serial import CommandPriority, _PendingCommand, SerialManager
        from tts160_types import CommandType
        import threading
        import heapq

        queue = []
        iterations = 1000

        start = time.perf_counter()

        # Insert with various priorities
        for i in range(iterations):
            priority = CommandPriority(i % 4)  # Cycle through priorities
            cmd = _PendingCommand(
                priority=priority,
                sequence=i,
                command=f':CMD{i}#',
                command_type=CommandType.BLIND,
                result_event=threading.Event()
            )
            heapq.heappush(queue, cmd)

        # Extract all
        results = []
        while queue:
            results.append(heapq.heappop(queue))

        elapsed = time.perf_counter() - start
        ops_per_sec = (iterations * 2) / elapsed  # Insert + extract

        print(f"\nPriority queue throughput: {ops_per_sec:.0f} ops/sec")

        # Verify ordering
        for i in range(1, len(results)):
            assert results[i-1] <= results[i], "Priority queue order violated"

        assert ops_per_sec > 10000, f"Queue throughput {ops_per_sec:.0f} below 10000 ops/sec"


class TestSerialParsingPerformance:
    """Benchmark binary parsing performance."""

    @pytest.mark.benchmark
    def test_binary_format_parsing(self):
        """Benchmark binary format string parsing."""
        from tts160_serial import BinaryParser

        iterations = 1000
        start = time.perf_counter()

        for _ in range(iterations):
            BinaryParser.parse_format_string('5i2f')

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nFormat string parsing: {ops_per_sec:.0f} ops/sec")
        assert ops_per_sec > 5000

    @pytest.mark.benchmark
    def test_binary_unpacking(self):
        """Benchmark binary data unpacking."""
        from tts160_serial import BinaryParser
        import struct

        # Create test data
        fmt = BinaryParser.create_format('test', '5i2f')
        data = struct.pack('<5i2f', 1, 2, 3, 4, 5, 1.5, 2.5)

        iterations = 10000
        start = time.perf_counter()

        for _ in range(iterations):
            BinaryParser.unpack_data(fmt, data)

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\nBinary unpacking: {ops_per_sec:.0f} ops/sec")
        assert ops_per_sec > 10000


class TestMemoryUsage:
    """Test memory efficiency."""

    @pytest.mark.benchmark
    def test_cache_memory_efficiency(self, mock_logger):
        """Measure cache memory usage."""
        from tts160_cache import TTS160Cache, CACHED_PROPERTIES
        import sys

        cache = TTS160Cache(mock_logger)

        # Populate all properties
        for i, prop in enumerate(CACHED_PROPERTIES):
            cache.update_property(prop, float(i))

        # Estimate size
        cache_size = sys.getsizeof(cache._cache)
        for key, value in cache._cache.items():
            cache_size += sys.getsizeof(key) + sys.getsizeof(value)

        print(f"\nCache memory usage: {cache_size} bytes for {len(CACHED_PROPERTIES)} properties")
        print(f"  ~{cache_size / len(CACHED_PROPERTIES):.1f} bytes per property")

        cache.stop_cache_thread()

        # Should be reasonably efficient
        assert cache_size < 10000, f"Cache uses {cache_size} bytes, expected < 10000"
