from pathlib import Path

from flask import Flask, jsonify, request

try:
    from .services import DashboardStore
except ImportError:  # pragma: no cover
    from services import DashboardStore


store = DashboardStore()


def create_app() -> Flask:
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    app = Flask(
        __name__,
        static_folder=str(frontend_dist) if frontend_dist.exists() else None,
        static_url_path="",
    )

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok"})

    @app.get("/")
    def root():
        if app.static_folder and (Path(app.static_folder) / "index.html").exists():
            return app.send_static_file("index.html")
        return jsonify(
            {
                "message": "Frontend build not found. Run the React client from the frontend folder or build it for static serving.",
            }
        )

    @app.post("/api/upload")
    def upload_files():
        uploads = request.files.getlist("files")
        if not uploads:
            return jsonify({"message": "No files uploaded."}), 400
        return jsonify(store.load_uploads(uploads))

    @app.get("/api/metadata")
    def metadata():
        return jsonify(store.get_metadata())

    @app.post("/api/sales/dashboard")
    def sales_dashboard():
        payload = request.get_json(silent=True) or {}
        return jsonify(store.sales_dashboard(payload))

    @app.post("/api/inventory/overview")
    def inventory_overview():
        payload = request.get_json(silent=True) or {}
        return jsonify(store.inventory_overview(payload))

    @app.post("/api/inventory/dio")
    def inventory_dio():
        payload = request.get_json(silent=True) or {}
        return jsonify(store.inventory_dio(payload))

    @app.post("/api/inventory/coverage")
    def inventory_coverage():
        payload = request.get_json(silent=True) or {}
        return jsonify(store.inventory_coverage(payload))

    @app.get("/<path:path>")
    def frontend(path: str):
        if app.static_folder and (Path(app.static_folder) / path).exists():
            return app.send_static_file(path)
        if app.static_folder and (Path(app.static_folder) / "index.html").exists():
            return app.send_static_file("index.html")
        return jsonify({"message": f"Route {path} not found."}), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)