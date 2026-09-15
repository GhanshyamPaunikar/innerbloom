"""Start Innerbloom's UI and API together, bound to this computer only."""
import argparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Innerbloom — your local journal")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--demo", action="store_true", help="Use temporary sample data and simulated AI, never your journal")
    args = parser.parse_args()
    import uvicorn
    if args.demo:
        from tests.preview_fixture import configure_demo
        app = configure_demo()
    else:
        from app import app
    print(f"Innerbloom: http://127.0.0.1:{args.port}/app", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
