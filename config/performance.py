from collections import defaultdict, deque
from datetime import datetime
import functools
import threading
import time
import tracemalloc

from django.db import connection


class PerformanceTracker:
    """
    In-memory, thread-safe Application Performance Monitor (APM).
    Captures request latencies, database query profiles, high-frequency call rates,
    function execution times, and memory footprint.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_tracker()
            return cls._instance

    def _init_tracker(self):
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.total_requests = 0
        self.request_history = deque(maxlen=1000)
        self.endpoint_stats = defaultdict(lambda: {
            "calls": 0,
            "total_time_ms": 0.0,
            "min_time_ms": float("inf"),
            "max_time_ms": 0.0,
            "total_db_queries": 0,
            "total_db_time_ms": 0.0,
            "slow_calls": 0,
            "last_called": None,
            "view_name": "",
            "timestamps": deque(maxlen=200),
        })
        self.function_stats = defaultdict(lambda: {
            "calls": 0,
            "total_time_ms": 0.0,
            "min_time_ms": float("inf"),
            "max_time_ms": 0.0,
            "last_called": None,
        })
        self.slow_queries = deque(maxlen=100)

        # Start heap tracking
        if not tracemalloc.is_tracing():
            try:
                tracemalloc.start()
            except Exception:
                pass

    def reset(self):
        with self.lock:
            self._init_tracker()

    def record_request(self, path, view_name, method, status_code, duration_ms, query_count, db_time_ms, query_log=None):
        now = time.time()
        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": now,
            "path": path,
            "view_name": view_name or path,
            "method": method,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "query_count": query_count,
            "db_time_ms": round(db_time_ms, 2),
        }

        with self.lock:
            self.total_requests += 1
            self.request_history.append(record)

            key = f"{method} {path.split('?')[0]}"
            stat = self.endpoint_stats[key]
            stat["calls"] += 1
            stat["total_time_ms"] += duration_ms
            stat["min_time_ms"] = min(stat["min_time_ms"], duration_ms)
            stat["max_time_ms"] = max(stat["max_time_ms"], duration_ms)
            stat["total_db_queries"] += query_count
            stat["total_db_time_ms"] += db_time_ms
            stat["last_called"] = record["timestamp"]
            stat["view_name"] = view_name or path
            stat["timestamps"].append(now)

            if duration_ms > 200.0:
                stat["slow_calls"] += 1

            # Log slow queries (> 25ms)
            if query_log:
                for q in query_log:
                    if q["duration_ms"] > 25.0:
                        self.slow_queries.append({
                            "sql": q["sql"],
                            "duration_ms": round(q["duration_ms"], 2),
                            "endpoint": key,
                            "timestamp": record["timestamp"],
                        })

    def record_function(self, func_name, duration_ms):
        with self.lock:
            stat = self.function_stats[func_name]
            stat["calls"] += 1
            stat["total_time_ms"] += duration_ms
            stat["min_time_ms"] = min(stat["min_time_ms"], duration_ms)
            stat["max_time_ms"] = max(stat["max_time_ms"], duration_ms)
            stat["last_called"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_metrics(self):
        with self.lock:
            now = time.time()
            uptime_seconds = max(1, int(now - self.start_time))

            # Requests in last 60 seconds (throughput)
            recent_requests_60s = sum(1 for r in self.request_history if now - r["epoch"] <= 60)
            req_per_min = recent_requests_60s

            # Latency statistics
            latencies = [r["duration_ms"] for r in self.request_history]
            avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            sorted_latencies = sorted(latencies)
            p95_index = int(len(sorted_latencies) * 0.95)
            p95_latency = round(sorted_latencies[p95_index], 2) if sorted_latencies else 0.0

            # DB statistics
            total_db_queries = sum(r["query_count"] for r in self.request_history)
            avg_queries_per_req = round(total_db_queries / len(self.request_history), 1) if self.request_history else 0.0

            # Memory metrics
            curr_mem_mb = 0.0
            peak_mem_mb = 0.0
            if tracemalloc.is_tracing():
                try:
                    curr_b, peak_b = tracemalloc.get_traced_memory()
                    curr_mem_mb = round(curr_b / (1024 * 1024), 2)
                    peak_mem_mb = round(peak_b / (1024 * 1024), 2)
                except Exception:
                    pass

            # Endpoints table
            endpoints_list = []
            high_frequency_endpoints = []
            for ep_key, stat in self.endpoint_stats.items():
                calls = stat["calls"]
                if calls == 0:
                    continue

                avg_ms = round(stat["total_time_ms"] / calls, 2)
                avg_db_q = round(stat["total_db_queries"] / calls, 1)
                avg_db_ms = round(stat["total_db_time_ms"] / calls, 2)

                # Calls in last 60s
                calls_last_60s = sum(1 for ts in stat["timestamps"] if now - ts <= 60)

                # Bottleneck assessment
                status = "OPTIMAL"
                recommendation = "Functioning within optimal latency parameters."
                if avg_ms > 250 or stat["max_time_ms"] > 1000:
                    status = "CRITICAL"
                    recommendation = "High response latency detected. Profile view logic, caching, and database queries."
                elif avg_db_q > 12:
                    status = "WARNING"
                    recommendation = "Potential N+1 database query pattern detected. Use select_related or prefetch_related."
                elif avg_ms > 100 or stat["slow_calls"] > (calls * 0.2):
                    status = "ATTENTION"
                    recommendation = "Moderate latency observed. Consider caching repetitive calculations."

                if calls_last_60s >= 10:
                    high_frequency_endpoints.append({
                        "endpoint": ep_key,
                        "view_name": stat["view_name"],
                        "calls_last_60s": calls_last_60s,
                        "avg_ms": avg_ms,
                        "optimization_advice": "High-frequency polling detected. Consider WebSocket or Server-Sent Events (SSE) to replace interval polling."
                    })

                endpoints_list.append({
                    "endpoint": ep_key,
                    "view_name": stat["view_name"],
                    "calls": calls,
                    "calls_last_60s": calls_last_60s,
                    "avg_ms": avg_ms,
                    "min_ms": round(stat["min_time_ms"], 2) if stat["min_time_ms"] != float("inf") else 0.0,
                    "max_ms": round(stat["max_time_ms"], 2),
                    "avg_db_queries": avg_db_q,
                    "avg_db_ms": avg_db_ms,
                    "slow_calls": stat["slow_calls"],
                    "status": status,
                    "recommendation": recommendation,
                    "last_called": stat["last_called"],
                })

            # Sort endpoints by total calls descending
            endpoints_list.sort(key=lambda x: x["calls"], reverse=True)

            # Function profiles table
            functions_list = []
            for fn_name, fstat in self.function_stats.items():
                fcalls = fstat["calls"]
                if fcalls == 0:
                    continue
                favg = round(fstat["total_time_ms"] / fcalls, 2)
                fmin = round(fstat["min_time_ms"], 2) if fstat["min_time_ms"] != float("inf") else 0.0
                fmax = round(fstat["max_time_ms"], 2)

                fstatus = "OPTIMAL"
                fadvice = "Optimal execution time."
                if favg > 50:
                    fstatus = "WARNING"
                    fadvice = "Computationally intensive function. Consider memoization, in-memory caching, or batch processing."
                elif favg > 20:
                    fstatus = "ATTENTION"
                    fadvice = "Noticeable CPU time. Optimize inner loops or database calls."

                functions_list.append({
                    "function_name": fn_name,
                    "calls": fcalls,
                    "total_ms": round(fstat["total_time_ms"], 2),
                    "avg_ms": favg,
                    "min_ms": fmin,
                    "max_ms": fmax,
                    "status": fstatus,
                    "advice": fadvice,
                    "last_called": fstat["last_called"],
                })

            functions_list.sort(key=lambda x: x["total_ms"], reverse=True)

            # Health index score (100 - penalties)
            penalty = 0
            if avg_latency > 200:
                penalty += 25
            elif avg_latency > 100:
                penalty += 10

            if avg_queries_per_req > 15:
                penalty += 20
            elif avg_queries_per_req > 8:
                penalty += 10

            if len(self.slow_queries) > 10:
                penalty += 15

            health_score = max(30, 100 - penalty)
            health_label = "Optimal" if health_score >= 85 else ("Moderate" if health_score >= 65 else "Degraded")

            return {
                "uptime_seconds": uptime_seconds,
                "total_requests": self.total_requests,
                "throughput_per_min": req_per_min,
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "avg_queries_per_req": avg_queries_per_req,
                "health_score": health_score,
                "health_label": health_label,
                "memory": {
                    "current_mb": curr_mem_mb,
                    "peak_mb": peak_mem_mb,
                },
                "endpoints": endpoints_list,
                "functions": functions_list,
                "high_frequency": high_frequency_endpoints,
                "slow_queries": list(self.slow_queries),
                "recent_requests": list(reversed(list(self.request_history)[-25:])),
            }


# Singleton instance
performance_tracker = PerformanceTracker()


def profile_function(name=None):
    """
    Decorator to automatically track execution duration and invocation counts
    of critical functions and services.
    """
    def decorator(func):
        metric_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000.0
                performance_tracker.record_function(metric_name, duration_ms)

        return wrapper
    return decorator


class PerformanceMonitoringMiddleware:
    """
    Django middleware for real-time request profiling and SQL query tracking.
    Attaches standard W3C Server-Timing headers to responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Exclude static/media files from APM tracking
        path = request.path_info
        if path.startswith("/static/") or path.startswith("/media/") or path == "/favicon.ico":
            return self.get_response(request)

        queries_executed = []
        db_start_total = 0.0

        def db_query_wrapper(execute, sql, params, many, context):
            q_start = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                q_dur = (time.perf_counter() - q_start) * 1000.0
                queries_executed.append({
                    "sql": str(sql),
                    "duration_ms": q_dur,
                })

        start_time = time.perf_counter()

        with connection.execute_wrapper(db_query_wrapper):
            response = self.get_response(request)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        query_count = len(queries_executed)
        db_time_ms = sum(q["duration_ms"] for q in queries_executed)

        # Resolve view name
        view_name = ""
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match:
            view_name = resolver_match.view_name or getattr(resolver_match.func, "__name__", "")

        # Record metrics
        performance_tracker.record_request(
            path=path,
            view_name=view_name,
            method=request.method,
            status_code=getattr(response, "status_code", 200),
            duration_ms=duration_ms,
            query_count=query_count,
            db_time_ms=db_time_ms,
            query_log=queries_executed,
        )

        # Attach W3C Server-Timing header for browser DevTools
        response["Server-Timing"] = f'total;dur={duration_ms:.1f}, db;dur={db_time_ms:.1f};desc="{query_count} queries"'

        return response
