"""AWS Lambda ASGI adapter for running FastAPI behind Amazon API Gateway."""

from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="off")
