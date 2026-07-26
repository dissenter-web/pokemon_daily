from fastapi import Request

from app.clients.max_api import MaxAPIClient


def get_max_client(request: Request) -> MaxAPIClient:
    return request.app.state.max_client

