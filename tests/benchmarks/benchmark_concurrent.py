"""
Concurrent load testing benchmarks.

Tests performance under concurrent access from multiple threads,
simulating multiple clients accessing the API simultaneously.

Run with: pytest tests/benchmarks/benchmark_concurrent.py -v --benchmark-only
"""

import pytest
import time
import threading
import statistics
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, MagicMock
from falcon import testing

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestConcurrentAPIAccess:
    """Test API performance under concurrent load."""

    @pytest.fixture
    def api_client(self, mock_logger):
        """Create test client with thread-safe mocked device."""
        import telescope
        import shr
        import exceptions
        from falcon import App

        mock_device = MagicMock()
        mock_device.Connected = True
        mock_device.RightAscension = 12.5
        mock_device.Declination = 45.0
        mock_device.Altitude = 60.0
        mock_device.Azimuth = 180.0
        mock_device.Slewing = False

        telescope.TTS160_dev = mock_device
        telescope.TTS160_cache = None
        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/rightascension', telescope.rightascension())
        app.add_route('/api/v1/telescope/{devnum:int}/declination', telescope.declination())
        app.add_route('/api/v1/telescope/{devnum:int}/altitude', telescope.altitude())
        app.add_route('/api/v1/telescope/{devnum:int}/slewing', telescope.slewing())

        return testing.TestClient(app)

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_concurrent_reads_same_property(self, api_client):
        """Test concurrent reads of the same property."""
        results = {'times': [], 'errors': 0}
        lock = threading.Lock()

        def make_request(client_id):
            start = time.perf_counter()
            try:
                response = api_client.simulate_get(
                    '/api/v1/telescope/{devnum:int}/rightascension',
                    params={'ClientID': str(client_id), 'ClientTransactionID': str(client_id)}
                )
                elapsed = time.perf_counter() - start

                with lock:
                    results['times'].append(elapsed * 1000)
                    if response.status != '200 OK':
                        results['errors'] += 1

            except Exception as e:
                with lock:
                    results['errors'] += 1

        # 10 concurrent workers, 100 requests each
        workers = 10
        requests_per_worker = 100

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for w in range(workers):
                for r in range(requests_per_worker):
                    client_id = w * 1000 + r
                    futures.append(executor.submit(make_request, client_id))

            for future in as_completed(futures):
                future.result()

        avg = statistics.mean(results['times'])
        p95 = sorted(results['times'])[int(len(results['times']) * 0.95)]
        total_requests = workers * requests_per_worker

        print(f"\nConcurrent reads ({workers} workers, {total_requests} total requests):")
        print(f"  Average latency: {avg:.3f}ms")
        print(f"  P95 latency: {p95:.3f}ms")
        print(f"  Errors: {results['errors']}")

        assert results['errors'] == 0, f"Had {results['errors']} errors"
        assert avg < 50, f"Average latency {avg:.3f}ms exceeds 50ms target"

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_concurrent_reads_different_properties(self, api_client):
        """Test concurrent reads of different properties."""
        endpoints = [
            '/api/v1/telescope/{devnum:int}/rightascension',
            '/api/v1/telescope/{devnum:int}/declination',
            '/api/v1/telescope/{devnum:int}/altitude',
            '/api/v1/telescope/{devnum:int}/slewing',
        ]

        results = {'times': [], 'errors': 0}
        lock = threading.Lock()

        def make_request(client_id, endpoint):
            start = time.perf_counter()
            try:
                response = api_client.simulate_get(
                    endpoint,
                    params={'ClientID': str(client_id), 'ClientTransactionID': str(client_id)}
                )
                elapsed = time.perf_counter() - start

                with lock:
                    results['times'].append(elapsed * 1000)
                    if response.status != '200 OK':
                        results['errors'] += 1

            except Exception:
                with lock:
                    results['errors'] += 1

        workers = 10
        requests_per_worker = 100

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for w in range(workers):
                for r in range(requests_per_worker):
                    client_id = w * 1000 + r
                    endpoint = endpoints[r % len(endpoints)]
                    futures.append(executor.submit(make_request, client_id, endpoint))

            for future in as_completed(futures):
                future.result()

        avg = statistics.mean(results['times'])
        p95 = sorted(results['times'])[int(len(results['times']) * 0.95)]

        print(f"\nConcurrent reads (different properties, {workers} workers):")
        print(f"  Average latency: {avg:.3f}ms")
        print(f"  P95 latency: {p95:.3f}ms")
        print(f"  Errors: {results['errors']}")

        assert results['errors'] == 0


class TestConcurrentCacheAccess:
    """Test cache performance under concurrent access."""

    @pytest.fixture
    def cache(self, mock_logger):
        """Create cache instance."""
        from tts160_cache import TTS160Cache
        cache = TTS160Cache(mock_logger)
        yield cache
        cache.stop_cache_thread()

    @pytest.mark.benchmark
    def test_concurrent_cache_updates(self, cache):
        """Test concurrent cache updates from multiple threads."""
        errors = []
        lock = threading.Lock()
        properties = ['RightAscension', 'Declination', 'Altitude', 'Azimuth', 'Tracking']

        def update_worker(worker_id):
            try:
                for i in range(1000):
                    prop = properties[i % len(properties)]
                    cache.update_property(prop, float(worker_id * 1000 + i))
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=update_worker, args=(w,)) for w in range(5)]

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        total_ops = 5 * 1000
        ops_per_sec = total_ops / elapsed

        print(f"\nConcurrent cache updates (5 threads, 1000 each):")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Throughput: {ops_per_sec:.0f} ops/sec")
        print(f"  Errors: {len(errors)}")

        assert len(errors) == 0

    @pytest.mark.benchmark
    def test_concurrent_cache_reads_writes(self, cache):
        """Test mixed concurrent reads and writes."""
        # Pre-populate cache
        for prop in ['RightAscension', 'Declination', 'Altitude', 'Azimuth', 'Tracking']:
            cache.update_property(prop, 0.0)

        read_count = [0]
        write_count = [0]
        errors = []
        lock = threading.Lock()

        def reader(worker_id):
            try:
                for i in range(500):
                    cache.get_property_value('RightAscension')
                    with lock:
                        read_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append(e)

        def writer(worker_id):
            try:
                for i in range(500):
                    cache.update_property('RightAscension', float(i))
                    with lock:
                        write_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = []
        for w in range(3):
            threads.append(threading.Thread(target=reader, args=(w,)))
        for w in range(2):
            threads.append(threading.Thread(target=writer, args=(w,)))

        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        total_ops = read_count[0] + write_count[0]
        ops_per_sec = total_ops / elapsed

        print(f"\nMixed cache access (3 readers, 2 writers):")
        print(f"  Reads: {read_count[0]}, Writes: {write_count[0]}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Throughput: {ops_per_sec:.0f} ops/sec")

        assert len(errors) == 0


class TestConcurrentPriorityQueue:
    """Test priority queue under concurrent access."""

    @pytest.mark.benchmark
    def test_concurrent_queue_operations(self, mock_logger):
        """Test priority queue with concurrent producers."""
        from tts160_serial import CommandPriority, _PendingCommand, SerialManager
        from tts160_types import CommandType
        import queue

        q = queue.PriorityQueue()
        produced = [0]
        consumed = [0]
        errors = []
        lock = threading.Lock()
        stop_event = threading.Event()

        def producer(producer_id):
            try:
                for i in range(100):
                    priority = CommandPriority(i % 4)
                    cmd = _PendingCommand(
                        priority=priority,
                        sequence=producer_id * 1000 + i,
                        command=f':CMD{i}#',
                        command_type=CommandType.BLIND,
                        result_event=threading.Event()
                    )
                    q.put(cmd)
                    with lock:
                        produced[0] += 1
            except Exception as e:
                with lock:
                    errors.append(e)

        def consumer():
            try:
                while not stop_event.is_set() or not q.empty():
                    try:
                        cmd = q.get(timeout=0.1)
                        with lock:
                            consumed[0] += 1
                    except queue.Empty:
                        continue
            except Exception as e:
                with lock:
                    errors.append(e)

        # Start consumer
        consumer_thread = threading.Thread(target=consumer)
        consumer_thread.start()

        # Start producers
        producer_threads = [threading.Thread(target=producer, args=(p,)) for p in range(5)]

        start = time.perf_counter()
        for t in producer_threads:
            t.start()
        for t in producer_threads:
            t.join()

        # Signal consumer to stop
        stop_event.set()
        consumer_thread.join()
        elapsed = time.perf_counter() - start

        print(f"\nConcurrent priority queue (5 producers, 1 consumer):")
        print(f"  Produced: {produced[0]}, Consumed: {consumed[0]}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Errors: {len(errors)}")

        assert len(errors) == 0
        assert produced[0] == consumed[0], "Not all produced items were consumed"


class TestSustainedLoad:
    """Test behavior under sustained load."""

    @pytest.fixture
    def api_client(self, mock_logger):
        """Create test client."""
        import telescope
        import shr
        import exceptions
        from falcon import App

        mock_device = MagicMock()
        mock_device.Connected = True
        mock_device.RightAscension = 12.5

        telescope.TTS160_dev = mock_device
        telescope.TTS160_cache = None
        telescope.logger = mock_logger
        shr.logger = mock_logger
        exceptions.logger = mock_logger

        app = App()
        app.add_route('/api/v1/telescope/{devnum:int}/rightascension', telescope.rightascension())

        return testing.TestClient(app)

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_sustained_request_rate(self, api_client):
        """Test sustained request rate over time."""
        duration_seconds = 5
        target_rate = 100  # requests per second

        results = {'times': [], 'errors': 0}
        lock = threading.Lock()
        stop_event = threading.Event()
        request_count = [0]

        def worker():
            while not stop_event.is_set():
                start = time.perf_counter()
                try:
                    response = api_client.simulate_get(
                        '/api/v1/telescope/{devnum:int}/rightascension',
                        params={'ClientID': '1', 'ClientTransactionID': '1'}
                    )
                    elapsed = time.perf_counter() - start

                    with lock:
                        results['times'].append(elapsed * 1000)
                        request_count[0] += 1
                        if response.status != '200 OK':
                            results['errors'] += 1
                except Exception:
                    with lock:
                        results['errors'] += 1

                # Rate limiting
                time.sleep(1.0 / target_rate)

        # Use multiple workers to achieve target rate
        workers = 5
        threads = [threading.Thread(target=worker) for _ in range(workers)]

        test_start = time.perf_counter()
        for t in threads:
            t.start()

        time.sleep(duration_seconds)
        stop_event.set()

        for t in threads:
            t.join()
        test_elapsed = time.perf_counter() - test_start

        actual_rate = request_count[0] / test_elapsed
        avg_latency = statistics.mean(results['times']) if results['times'] else 0

        print(f"\nSustained load test ({duration_seconds}s, target {target_rate} req/s):")
        print(f"  Actual rate: {actual_rate:.1f} req/s")
        print(f"  Total requests: {request_count[0]}")
        print(f"  Average latency: {avg_latency:.3f}ms")
        print(f"  Errors: {results['errors']}")

        assert results['errors'] == 0
