"""HTTP signaling routes for WebRTC offer/answer exchange."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

import numpy as np
from aiohttp import web
from aiortc import RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

from ergos.transport.audio_track import TTSAudioTrack
from ergos.transport.connection import ConnectionManager
from ergos.transport.data_channel import DataChannelHandler

logger = logging.getLogger(__name__)


async def _process_incoming_audio(
    track,
    callback: Optional[Callable[[np.ndarray, int], None]],
) -> None:
    """
    Process incoming audio frames from a WebRTC track.

    Args:
        track: The incoming audio track from the client.
        callback: Optional callback for processing audio samples.
            Called with (samples: np.ndarray, sample_rate: int).
    """
    while True:
        try:
            frame = await track.recv()
            if callback:
                # Convert AudioFrame to numpy array
                # frame.to_ndarray() returns shape (channels, samples)
                samples = frame.to_ndarray()

                logger.debug(
                    f"Raw frame: format={frame.format.name}, layout={frame.layout.name}, "
                    f"frame.samples={frame.samples}, sample_rate={frame.sample_rate}, "
                    f"ndarray shape={samples.shape}, dtype={samples.dtype}"
                )

                # Handle different audio formats:
                # - Planar formats (s16p, fltp): shape = (channels, samples_per_channel)
                # - Packed/Interleaved formats (s16, flt): shape = (1, samples * channels)
                #   where samples are interleaved: L0,R0,L1,R1,...

                is_planar = frame.format.is_planar
                num_channels = len(frame.layout.channels)

                if samples.ndim > 1:
                    samples = samples[0]  # Flatten to 1D first

                if not is_planar and num_channels == 2:
                    # Interleaved stereo: LRLRLR... - take every other sample for mono
                    # CRITICAL: Use .copy() to create contiguous array, not a strided view.
                    # Strided views (samples[::2]) are non-contiguous and cause segfaults
                    # when passed to native code (av/ffmpeg).
                    samples = samples[::2].copy()  # Take left channel samples
                elif is_planar and samples.ndim > 1:
                    # Planar: shape was (channels, samples), already flattened above
                    logger.debug(f"Planar audio, using channel 0: {len(samples)} samples")

                # Handle both int16 and float audio formats from WebRTC
                # Opus decoder typically outputs s16 (int16), but some configurations
                # may produce float audio in [-1, 1] range
                if samples.dtype in (np.float32, np.float64):
                    # Float audio in [-1, 1] range - convert to int16
                    logger.debug(
                        f"Converting float audio (dtype={samples.dtype}, "
                        f"range=[{samples.min():.4f}, {samples.max():.4f}]) to int16"
                    )
                    samples = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
                elif samples.dtype != np.int16:
                    # Other integer types - clip and convert
                    samples = np.clip(samples, -32768, 32767).astype(np.int16)
                # else: already int16, use as-is

                # Final safety check: ensure array is C-contiguous before passing
                # to callback (which may use native code that requires contiguous memory)
                if not samples.flags['C_CONTIGUOUS']:
                    samples = np.ascontiguousarray(samples)

                await callback(samples, frame.sample_rate)
        except MediaStreamError:
            logger.info("Incoming audio track ended")
            break
        except Exception as e:
            logger.error(f"Error processing incoming audio: {e}")
            break


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
    data_handler: DataChannelHandler = request.app["data_handler"]
    on_incoming_audio: Optional[Callable] = request.app.get("on_incoming_audio")

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

        # Reset pipeline state for new connection (fixes stuck state after reconnect)
        on_connect = request.app.get("on_connect")
        if on_connect:
            await on_connect()

        # Create peer connection
        pc = await manager.create_connection()

        # Create and add outbound TTS audio track BEFORE createAnswer()
        # This is critical per RESEARCH.md pitfall #6
        tts_track = TTSAudioTrack(sample_rate=24000)
        pc.addTrack(tts_track)
        manager.register_track(pc, tts_track)
        logger.info("Added TTS audio track to connection")

        # Register handler for incoming audio track
        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                logger.info("Received incoming audio track")
                asyncio.create_task(
                    _process_incoming_audio(track, on_incoming_audio)
                )

        # Register handler for data channel
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"Data channel '{channel.label}' created by client")
            data_handler.register_channel(channel)
            manager.track_data_channel(channel)

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


def create_signaling_app(
    manager: ConnectionManager,
    data_handler: DataChannelHandler,
    on_incoming_audio: Optional[Callable[[np.ndarray, int], None]] = None,
) -> web.Application:
    """
    Create an aiohttp Application with signaling routes.

    The signaling app handles WebRTC offer/answer exchange and sets up:
    - Outbound TTS audio track for each connection
    - Incoming audio track handling with optional callback
    - Data channel routing to the provided handler

    Args:
        manager: The ConnectionManager to use for peer connections.
        data_handler: The DataChannelHandler for routing data channel messages.
        on_incoming_audio: Optional async callback for incoming audio frames.
            Called with (samples: np.ndarray, sample_rate: int).

    Returns:
        Configured aiohttp Application with /offer route.
    """
    app = web.Application()
    app["manager"] = manager
    app["data_handler"] = data_handler
    app["on_incoming_audio"] = on_incoming_audio

    # Register routes
    app.router.add_post("/offer", offer)

    # Register shutdown handler
    app.on_shutdown.append(on_shutdown)

    logger.info("Created signaling app with /offer endpoint")
    return app
