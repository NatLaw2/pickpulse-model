"""Churn Risk Engine — Console launcher.

Usage:
    python -m app.console
    python -m app.console --port 8000
"""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Churn Risk Engine Console")
    parser.add_argument("--port", type=int, default=8000, help="API port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Churn Risk Engine — Console")
    print("=" * 60)
    print()
    print(f"  Backend API:  http://localhost:{args.port}")
    print(f"  Frontend:     http://localhost:5173")
    print()
    print("  Starting backend server...")
    print()

    # Generate sample dataset if it doesn't exist
    sample_dir = "data/sample"
    if not os.path.exists(os.path.join(sample_dir, "churn_customers.csv")):
        print("  Generating sample dataset...")
        from .engine.sample_data import save_sample_datasets
        save_sample_datasets()
        print("  Done.")
        print()

    import uvicorn
    uvicorn.run(
        "app.console_api:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
