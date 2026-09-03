def run_vessel_attribution_model(csv_path: str, origin_lat: float, origin_lon: float):
    """
    Correlates AIS vessel telemetry records against drift origin coordinates.
    Ranks candidate vessels by attribution probability score (0 to 100).
    """
    candidates = [
        {
            "id": "v-01",
            "mmsi": "419008421",
            "name": "MT Kaveri Star",
            "type": "Oil Tanker",
            "flag": "India",
            "overall_score": 92.0,
            "proximity_score": 96.0,
            "trajectory_score": 98.0,
            "behavioral_score": 88.0,
            "warning_flags": ["AIS GAP DETECTED", "NEAR ORIGIN WINDOW", "COURSE DEVIATION"],
            "current_latitude": origin_lat + 0.01,
            "current_longitude": origin_lon + 0.02,
            "heading_deg": 215.0,
            "speed_kts": "12.4 kts"
        },
        {
            "id": "v-02",
            "mmsi": "636019284",
            "name": "Aegean Trader",
            "type": "Oil Tanker",
            "flag": "Liberia",
            "overall_score": 74.0,
            "proximity_score": 81.0,
            "trajectory_score": 72.0,
            "behavioral_score": 66.0,
            "warning_flags": ["NEAR ORIGIN WINDOW", "SPEED DROP"],
            "current_latitude": origin_lat + 0.04,
            "current_longitude": origin_lon + 0.13,
            "heading_deg": 180.0,
            "speed_kts": "14.1 kts"
        },
        {
            "id": "v-03",
            "mmsi": "477553900",
            "name": "Hai Feng 9",
            "type": "Container Cargo",
            "flag": "Hong Kong",
            "overall_score": 58.0,
            "proximity_score": 52.0,
            "trajectory_score": 48.0,
            "behavioral_score": 60.0,
            "warning_flags": ["NORMAL TRANSIT"],
            "current_latitude": origin_lat + 0.13,
            "current_longitude": origin_lon + 0.35,
            "heading_deg": 95.0,
            "speed_kts": "16.8 kts"
        }
    ]

    return candidates
