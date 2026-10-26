"""Deterministic perception for the procedural AV-TRACE video frames."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .types import DecodedMedia, DecodedVideoFrame, Observation, TimeInterval


VISUAL_ADAPTER_VERSION = "synthetic-pixel-vision/1.0.0"

_PALETTE = {
    "blue": (47, 125, 246),
    "green": (66, 214, 107),
    "red": (239, 65, 65),
    "yellow": (255, 212, 59),
    "cobalt": (53, 107, 196),
    "orange": (255, 146, 43),
}
_TEXT_VOCABULARY = (
    "BLUE",
    "GREEN",
    "RED",
    "YELLOW",
    "COBALT",
    "ORANGE",
    "TRIANGLE",
    "CIRCLE",
    "SQUARE",
    "STAR",
    "ARROW",
    "HEXAGON",
    "POINTS",
    "RIGHT",
    "LEFT",
    "UP",
    "DOWN",
    "ZERO",
    "ONE",
    "TWO",
    "THREE",
    "FOUR",
    "FIVE",
    "SIX",
    "SEVEN",
    "EIGHT",
    "NINE",
    "TEN",
)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _render_template(text: str, *, font_size: int, width: int, height: int) -> np.ndarray:
    font = _font(font_size)
    canvas = Image.new("L", (max(width * 4, 40), max(height * 2, 30)), 0)
    ImageDraw.Draw(canvas).text((2, 2), text, font=font, fill=255)
    return _normalize_binary(np.asarray(canvas) > 127, width=width, height=height)


def _segments(active: np.ndarray, minimum_gap: int = 3) -> list[tuple[int, int]]:
    indexes = np.flatnonzero(active)
    if indexes.size == 0:
        return []
    result: list[tuple[int, int]] = []
    start = int(indexes[0])
    previous = start
    for value in indexes[1:]:
        value = int(value)
        if value - previous > minimum_gap:
            result.append((start, previous + 1))
            start = value
        previous = value
    result.append((start, previous + 1))
    return result


def _normalize_binary(mask: np.ndarray, width: int = 280, height: int = 30) -> np.ndarray:
    ys, xs = np.where(mask)
    if not len(xs):
        return np.zeros((height, width), dtype=bool)
    cropped = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    image = Image.fromarray((cropped * 255).astype(np.uint8), mode="L")
    image.thumbnail((width, height), resample=Image.Resampling.NEAREST)
    canvas = np.zeros((height, width), dtype=np.uint8)
    data = np.asarray(image)
    y = (height - data.shape[0]) // 2
    x = (width - data.shape[1]) // 2
    canvas[y : y + data.shape[0], x : x + data.shape[1]] = data
    return canvas > 127


@lru_cache(maxsize=None)
def _word_template(word: str) -> np.ndarray:
    font = _font(17)
    canvas = Image.new("L", (420, 40), 0)
    draw = ImageDraw.Draw(canvas)
    draw.text((2, 2), word, font=font, fill=255)
    return _normalize_binary(np.asarray(canvas) > 127)


def _binary_similarity(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    if not union:
        return 0.0
    return float(np.logical_and(left, right).sum() / union)


def _read_label_tokens(rgb: np.ndarray) -> tuple[list[str], float]:
    height, width, _ = rgb.shape
    # The synthetic event caption is a burned-in visual line immediately above
    # the progress bar.  This fixed screen region is a media-format property,
    # not an annotation lookup.
    region = rgb[int(height * 0.66) : int(height * 0.87), int(width * 0.03) : int(width * 0.97)]
    white = (region.min(axis=2) > 165) & ((region.max(axis=2) - region.min(axis=2)) < 45)
    rows = _segments(white.sum(axis=1) >= 2, minimum_gap=1)
    if not rows:
        return [], 0.0
    y0, y1 = max(rows, key=lambda item: int(white[item[0] : item[1]].sum()))
    line = white[y0:y1]
    words = _segments(line.sum(axis=0) > 0, minimum_gap=6)
    tokens: list[str] = []
    scores: list[float] = []
    for x0, x1 in words:
        candidate = _normalize_binary(line[:, x0:x1])
        token, score = max(
            ((word, _binary_similarity(candidate, _word_template(word))) for word in _TEXT_VOCABULARY),
            key=lambda item: item[1],
        )
        if score >= 0.50:
            tokens.append(token)
            scores.append(score)
    return tokens, float(np.mean(scores)) if scores else 0.0


def _read_visible_counter(rgb: np.ndarray) -> tuple[list[str], float]:
    height, width, _ = rgb.shape
    region = rgb[0 : int(height * 0.18), int(width * 0.70) : width]
    white = (region.min(axis=2) > 125) & ((region.max(axis=2) - region.min(axis=2)) < 60)
    rows = _segments(white.sum(axis=1) > 0, minimum_gap=1)
    if not rows:
        return [], 0.0
    y0, y1 = max(rows, key=lambda item: int(white[item[0] : item[1]].sum()))
    line = white[y0:y1]
    characters = _segments(line.sum(axis=0) > 0, minimum_gap=1)
    tokens: list[str] = []
    scores: list[float] = []
    for x0, x1 in characters:
        candidate = _normalize_binary(line[:, x0:x1], width=20, height=20)
        token, score = max(
            (
                (symbol, _binary_similarity(candidate, _render_template(symbol, font_size=12, width=20, height=20)))
                for symbol in "0123456789"
            ),
            key=lambda item: item[1],
        )
        if score >= 0.70:
            tokens.append(token)
            scores.append(score)
    return tokens, float(np.mean(scores)) if scores else 0.0


def _component_from_pixels(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
    height, width, _ = rgb.shape
    roi = rgb[int(height * 0.18) : int(height * 0.74), int(width * 0.12) : int(width * 0.88)].astype(np.int16)
    border = np.concatenate((roi[:3].reshape(-1, 3), roi[-3:].reshape(-1, 3), roi[:, :3].reshape(-1, 3), roi[:, -3:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    distance = np.linalg.norm(roi - background, axis=2)
    chroma = roi.max(axis=2) - roi.min(axis=2)
    mask = (distance > 42) & (chroma > 38) & (roi.max(axis=2) > 90)
    ys, xs = np.where(mask)
    if xs.size < 150:
        return None
    # The generated scene has one central colored object.  Restricting to its
    # bounding box also rejects white outlines and captions.
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    component = mask[y0:y1, x0:x1]
    colors = roi[y0:y1, x0:x1][component]
    median_color = np.median(colors, axis=0)
    palette = np.asarray(list(_PALETTE.values()), dtype=np.float64)
    distances = np.linalg.norm(palette - median_color, axis=1)
    color_index = int(np.argmin(distances))
    return component, median_color, float(distances[color_index])


def _classify_shape(mask: np.ndarray) -> tuple[str, str | None, float]:
    height, width = mask.shape
    occupancy = float(mask.mean())
    ys, xs = np.where(mask)
    centroid_y = float(ys.mean() / max(1, height - 1))
    aspect = width / max(1, height)
    if occupancy > 0.90:
        return "square", None, 0.99
    if centroid_y > 0.60:
        return "triangle", None, 0.97
    if occupancy < 0.49:
        return "star", None, 0.94
    if occupancy < 0.66:
        edge = max(
            {
                "left": float(mask[:, : max(1, width // 12)].mean()),
                "right": float(mask[:, -max(1, width // 12) :].mean()),
                "up": float(mask[: max(1, height // 12), :].mean()),
                "down": float(mask[-max(1, height // 12) :, :].mean()),
            }.items(),
            key=lambda item: item[1],
        )[0]
        direction = {"left": "right", "right": "left", "up": "down", "down": "up"}[edge]
        return "arrow", direction, 0.93
    if aspect > 1.08:
        return "hexagon", None, 0.93
    return "circle", None, 0.93


@dataclass(frozen=True)
class _FrameDetection:
    interval: TimeInterval
    shape: str
    color: str
    arrow_direction: str | None
    visible_tokens: tuple[str, ...]
    numeric_tokens: tuple[str, ...]
    confidence: float


class SyntheticVisualAdapter:
    """Recognize procedural shapes and burned-in tokens directly from pixels."""

    name = "synthetic_pixel_vision"
    version = VISUAL_ADAPTER_VERSION

    def detect_frame(self, frame: DecodedVideoFrame) -> _FrameDetection | None:
        component = _component_from_pixels(frame.rgb)
        if component is None:
            return None
        mask, _median_color, color_distance = component
        palette_names = tuple(_PALETTE)
        palette_values = np.asarray(tuple(_PALETTE.values()), dtype=np.float64)
        object_pixels = frame.rgb.reshape(-1, 3).astype(np.float64)
        # Recompute color choice from the pixels nearest a supported palette,
        # avoiding any source/event metadata.
        mean_distances = np.percentile(
            np.linalg.norm(object_pixels[:, None, :] - palette_values[None, :, :], axis=2),
            2,
            axis=0,
        )
        color = palette_names[int(np.argmin(mean_distances))]
        shape, direction, shape_confidence = _classify_shape(mask)
        tokens, text_confidence = _read_label_tokens(frame.rgb)
        counter_tokens, counter_confidence = _read_visible_counter(frame.rgb)
        color_confidence = max(0.0, 1.0 - color_distance / 80.0)
        confidence = 0.45 * shape_confidence + 0.35 * color_confidence + 0.20 * text_confidence
        return _FrameDetection(
            interval=frame.interval,
            shape=shape,
            color=color,
            arrow_direction=direction,
            visible_tokens=tuple(tokens),
            numeric_tokens=tuple(counter_tokens),
            confidence=min(1.0, confidence + counter_confidence * 0.02),
        )

    def observe(self, decoded: DecodedMedia) -> list[Observation]:
        detections = [item for frame in decoded.video_frames if (item := self.detect_frame(frame)) is not None]
        if not detections:
            return []
        groups: list[list[_FrameDetection]] = []
        for item in detections:
            key = (item.shape, item.color, item.arrow_direction, item.visible_tokens)
            previous_key = (
                (groups[-1][-1].shape, groups[-1][-1].color, groups[-1][-1].arrow_direction, groups[-1][-1].visible_tokens)
                if groups
                else None
            )
            if groups and key == previous_key and item.interval.start_s <= groups[-1][-1].interval.end_s + 1e-6:
                groups[-1].append(item)
            else:
                groups.append([item])

        observations: list[Observation] = []
        for group in groups:
            first, last = group[0], group[-1]
            tokens = list(first.visible_tokens)
            observations.append(
                Observation(
                    modality="vision",
                    interval=TimeInterval(first.interval.start_s, last.interval.end_s),
                    confidence=float(np.mean([item.confidence for item in group])),
                    adapter_name=self.name,
                    adapter_version=self.version,
                    media_hash=decoded.media_hash,
                    decoded_interval=decoded.requested_interval,
                    content={
                        "shape": first.shape,
                        "color": first.color,
                        "arrow_direction": first.arrow_direction,
                        "visible_text": " ".join(tokens),
                        "visible_tokens": tokens,
                        "numeric_tokens": list(first.numeric_tokens),
                    },
                )
            )
        return observations
