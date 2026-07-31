"""Thin EdgeOne route adapter for the reader controller."""

from .._controllers.reader_controller import handler as handle_reader


async def handler(ctx):
    return await handle_reader(ctx)
