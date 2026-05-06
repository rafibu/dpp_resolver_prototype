import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="factory",
        description="DPP Platform Factory - spawns and manages platform containers via REST API",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8090, help="Port to bind (default: 8090)")
    parser.add_argument(
        "--federation-config",
        default="default-federation.yml",
        metavar="FILE",
        help="Path to federation YAML config (default: default-federation.yml)",
    )
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "dpp_platform_factory.main:app",
        host=args.host,
        port=args.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
