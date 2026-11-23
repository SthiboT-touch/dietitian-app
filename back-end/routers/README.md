# API Routers

FastAPI route modules are organized here by application area, including authentication and administration, clients, appointments, care, meal planning, AI, and staff access. The application entry point in [`../app.py`](../app.py) includes these routers.

Keep endpoint behavior and request/response models aligned with [`../schemas.py`](../schemas.py), and enforce authorization at the route or owning service boundary.