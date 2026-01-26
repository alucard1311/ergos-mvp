"""HTTP signaling routes for WebRTC offer/answer exchange."""

from __future__ import annotations

import logging

from aiohttp import web
from aiortc import RTCSessionDescription

from ergos.transport.connection import ConnectionManager

logger = logging.getLogger(__name__)


async def offer(request: web.Request) -> web.Response:
    """
    Handle WebRTC offer and return SDP answer.

    Expects JSON body:
        {"sdp": "...", "type": "offer"}

    Returns JSON response:
        {"sdp": "...", "type": "answer"}

    Args:
        request: The aiohttp request object.

    Returns:
        JSON response with SDP answer or error.
    """
    manager: ConnectionManager = request.app["manager"]

    # Parse request body
    try:
        params = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON in offer request: {e}")
        return web.json_response(
            {"error": "Invalid JSON body"},
            status=400,
        )

    # Validate required fields
    sdp = params.get("sdp")
    offer_type = params.get("type")

    if not sdp:
        return web.json_response(
            {"error": "Missing 'sdp' field"},
            status=400,
        )

    if offer_type != "offer":
        return web.json_response(
            {"error": "Expected type 'offer'"},
            status=400,
        )

    try:
        # Create session description from offer
        offer_desc = RTCSessionDescription(sdp=sdp, type=offer_type)

        # Create peer connection
        pc = await manager.create_connection()

        # Set remote description (the offer)
        await pc.setRemoteDescription(offer_desc)

        # Create and set local description (the answer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logger.info("Processed offer, returning answer")

        return web.json_response({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        })

    except Exception as e:
        logger.error(f"Error processing offer: {e}")
        return web.json_response(
            {"error": f"Connection error: {str(e)}"},
            status=500,
        )


async def on_shutdown(app: web.Application) -> None:
    """Close all connections on app shutdown."""
    manager: ConnectionManager = app["manager"]
    await manager.close_all()


def create_signaling_app(manager: ConnectionManager) -> web.Application:
    """
    Create an aiohttp Application with signaling routes.

    Args:
        manager: The ConnectionManager to use for peer connections.

    Returns:
        Configured aiohttp Application with /offer route.
    """
    app = web.Application()
    app["manager"] = manager

    # Register routes
    app.router.add_post("/offer", offer)

    # Register shutdown handler
    app.on_shutdown.append(on_shutdown)

    logger.info("Created signaling app with /offer endpoint")
    return app
