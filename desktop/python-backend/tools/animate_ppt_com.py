"""
PPT Animation COM Backend — Windows PowerPoint COM 自动化
==========================================================
通过 pywin32 调用 PowerPoint COM API 添加动画。
仅在 Windows + 已安装 PowerPoint 时可用。

比 XML 注入更可靠，因为使用 PowerPoint 自身引擎。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

_log = logging.getLogger(__name__)

# COM effect type mappings
# PowerPoint MsoAnimEffect enum values
COM_EFFECTS = {
    # Entrance
    "appear":           10,   # msoAnimEffectAppear
    "fade":             10,   # msoAnimEffectFade (same ID, different subtype)
    "fly_in":           2,    # msoAnimEffectFly
    "wipe":             22,   # msoAnimEffectWipe
    "zoom":             53,   # msoAnimEffectZoom
    "float_up":         29,   # msoAnimEffectFloat (up)
    "float_down":       29,   # msoAnimEffectFloat (down)
    "split_vertical":   17,   # msoAnimEffectSplit
    "split_horizontal": 17,   # msoAnimEffectSplit
    "blinds_horizontal": 3,   # msoAnimEffectBlinds
    "blinds_vertical":  3,    # msoAnimEffectBlinds
    "checkerboard":     4,    # msoAnimEffectCheckerboard
    "circle":           5,    # msoAnimEffectCircle
    "diamond":          6,    # msoAnimEffectDiamond
    "plus":             18,   # msoAnimEffectPlus
    "dissolve":         7,    # msoAnimEffectDissolve
    "random_bars":      9,    # msoAnimEffectRandomBars
    "peek_up":          19,   # msoAnimEffectPeek
    "peek_down":        19,
    "peek_left":        19,
    "peek_right":       19,
    "grow_turn":        28,   # msoAnimEffectGrowAndTurn
    "swivel":           30,   # msoAnimEffectSwivel
    "expand":           54,   # msoAnimEffectExpand
    "spin":             55,   # msoAnimEffectSpin
    "rise_up":          57,   # msoAnimEffectRiseUp
    "bouncy":           58,   # msoAnimEffectBounce
    # Exit
    "disappear":        10,
    "fade_out":         10,
    "fly_out":          2,
    "wipe_out":         22,
    "zoom_out":         53,
    "float_down_exit":  29,
    "split_out_v":      17,
    "split_out_h":      17,
    "dissolve_out":     7,
    "random_bars_out":  9,
    "collapse_exit":    61,
    "spin_exit":        55,
    # Emphasis
    "pulse":            22,
    "color_pulse":      2,
    "grow":             19,
    "shrink":           19,
    "spin_cw":          30,
    "spin_ccw":         30,
    "transparency":     32,
    "desaturate":       36,
    "darken":           37,
    "lighten":          37,
}

# Trigger type mappings
COM_TRIGGERS = {
    "onclick":    1,  # msoAnimTriggerOnPageClick
    "withprev":   3,  # msoAnimTriggerWithPrevious
    "afterprev":  4,  # msoAnimTriggerAfterPrevious
}

# Slide transition mappings (ppEntryEffect)
COM_TRANSITIONS = {
    "fade":             3849,  # ppEffectFade
    "push":             3850,  # ppEffectPush
    "wipe":             3851,  # ppEffectWipe
    "split":            3852,  # ppEffectSplit
    "blinds":           3853,  # ppEffectBlinds
    "checkerboard":     3854,  # ppEffectCheckerboard
    "circle":           3855,  # ppEffectCircle
    "diamond":          3856,  # ppEffectDiamond
    "dissolve":         3857,  # ppEffectDissolve
    "cover":            3858,  # ppEffectCover
    "uncover":          3859,  # ppEffectUncover
    "random":           3860,  # ppEffectRandom
    "zoom":             3861,  # ppEffectZoom
    "grow_and_turn":    3862,  # ppEffectGrowAndTurn
    "flip":             3863,  # ppEffectFlip
    "gallery":          3864,  # ppEffectGallery
    "convey":           3865,  # ppEffectConvey
    "rotate":           3866,  # ppEffectRotate
    "cube":             3867,  # ppEffectCube
    "box":              3868,  # ppEffectBox
    "pan":              3869,  # ppEffectPan
    "glitter":          3870,  # ppEffectGlitter
    "honeycomb":        3871,  # ppEffectHoneycomb
    "morph":            3872,  # ppEffectMorph
}


def is_com_available() -> bool:
    """Check if PowerPoint COM automation is available (Windows only)."""
    if not __import__("sys").platform == "win32":
        return False
    try:
        import win32com.client
        # Try to connect to PowerPoint
        try:
            ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            return True
        except Exception:
            # PowerPoint not running, try to create
            try:
                ppt = win32com.client.Dispatch("PowerPoint.Application")
                ppt.Quit()
                return True
            except Exception:
                return False
    except ImportError:
        return False


def add_animations_com(
    pptx_path: str,
    animations: list[dict],
    output: Optional[str] = None,
    transitions: Optional[list[dict]] = None,
) -> dict:
    """Add animations using PowerPoint COM API (Windows only).
    
    This is more reliable than XML injection because it uses PowerPoint's
    own engine to generate the animation XML.
    """
    try:
        import win32com.client
        from win32com.client import constants as c
    except ImportError:
        return {"error": "pywin32 not installed", "success": False, "backend": "com"}

    if not os.path.isfile(pptx_path):
        return {"error": f"File not found: {pptx_path}", "success": False}

    if not output:
        base, ext = os.path.splitext(pptx_path)
        output = f"{base}_animated{ext}"

    abs_path = os.path.abspath(pptx_path)
    abs_output = os.path.abspath(output)

    ppt = None
    pres = None
    try:
        # Launch PowerPoint
        ppt = win32com.client.Dispatch("PowerPoint.Application")
        ppt.Visible = True

        # Open presentation
        pres = ppt.Presentations.Open(abs_path, WithWindow=False)

        slides_animated = 0
        shapes_animated = 0
        shapes_failed = 0
        transitions_failed = 0

        # Apply animations
        for anim_spec in animations:
            slide_num = anim_spec.get("slide", 1)
            effect_name = anim_spec.get("effect", "fade")
            target = anim_spec.get("target", "all_text")
            duration = anim_spec.get("duration", 0.5)
            delay = anim_spec.get("delay", 0)
            trigger = anim_spec.get("trigger", "afterprev")

            if slide_num < 1 or slide_num > pres.Slides.Count:
                _log.warning("Slide %d out of range (1-%d)", slide_num, pres.Slides.Count)
                continue

            slide = pres.Slides(slide_num)
            effect_id = COM_EFFECTS.get(effect_name.lower())
            trigger_id = COM_TRIGGERS.get(trigger.lower(), 4)

            if effect_id is None:
                _log.warning("Unknown effect: %s", effect_name)
                continue

            # Select shapes based on target
            shape_indices = _select_com_shapes(slide, target)
            if not shape_indices:
                _log.warning("No shapes matched target '%s' on slide %d", target, slide_num)
                continue

            for idx, shape_idx in enumerate(shape_indices):
                try:
                    shape = slide.Shapes(shape_idx)
                    effect = slide.TimeLine.MainSequence.AddEffect(
                        Shape=shape,
                        effectId=effect_id,
                        trigger=trigger_id,
                    )
                    # Set timing
                    effect.Timing.Duration = duration
                    effect.Timing.TriggerDelayTime = delay + (idx * 0.1)

                    # Set direction for directional effects
                    if "float_down" in effect_name or "down" in effect_name:
                        try:
                            effect.EffectParameters.Direction = 2  # down
                        except Exception:
                            pass
                    elif "float_left" in effect_name or "left" in effect_name:
                        try:
                            effect.EffectParameters.Direction = 4  # left
                        except Exception:
                            pass
                    elif "float_right" in effect_name or "right" in effect_name:
                        try:
                            effect.EffectParameters.Direction = 8  # right
                        except Exception:
                            pass

                    shapes_animated += 1
                except Exception as e:
                    shapes_failed += 1
                    _log.warning("Failed to animate shape %d on slide %d: %s",
                                 shape_idx, slide_num, e)

            slides_animated += 1

        # Apply transitions
        if transitions:
            for t in transitions:
                slide_num = t.get("slide", 1)
                trans_type = t.get("type", "fade")
                duration = t.get("duration", 1.0)

                if slide_num < 1 or slide_num > pres.Slides.Count:
                    continue

                slide = pres.Slides(slide_num)
                trans_id = COM_TRANSITIONS.get(trans_type.lower())

                if trans_id is not None:
                    try:
                        slide.SlideShowTransition.EntryEffect = trans_id
                        slide.SlideShowTransition.Duration = duration
                        slide.SlideShowTransition.AdvanceOnClick = True
                    except Exception as e:
                        transitions_failed += 1
                        _log.warning("Failed to set transition on slide %d: %s", slide_num, e)

        # Save
        pres.SaveAs(abs_output)
        pres.Close()

        return {
            "success": True,
            "path": abs_output,
            "slides_animated": slides_animated,
            "shapes_animated": shapes_animated,
            "shapes_failed": shapes_failed,
            "transitions_failed": transitions_failed,
            "backend": "com",
        }

    except Exception as e:
        _log.error("COM animation failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False, "backend": "com"}

    finally:
        try:
            if pres:
                pres.Close()
        except Exception:
            pass
        try:
            if ppt:
                ppt.Quit()
        except Exception:
            pass


def _select_com_shapes(slide, target: str) -> list[int]:
    """Select shape indices from a COM slide object."""
    indices = []
    total = slide.Shapes.Count

    if target == "all":
        return list(range(1, total + 1))

    if target == "all_text":
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                if shape.HasTextFrame:
                    if shape.TextFrame.HasText:
                        indices.append(i)
                elif shape.HasTable:
                    indices.append(i)
            except Exception:
                pass
        if not indices:
            indices = list(range(1, total + 1))
        return indices

    if target == "all_images":
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                if shape.Type == 13:  # msoPicture
                    indices.append(i)
            except Exception:
                pass
        return indices

    if target == "all_charts":
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                if shape.HasChart:
                    indices.append(i)
            except Exception:
                pass
        return indices

    if target == "title":
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                if shape.PlaceholderFormat.Type == 1:  # ppPlaceholderTitle
                    indices.append(i)
            except Exception:
                pass
        return indices

    if target == "body":
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                ptype = shape.PlaceholderFormat.Type
                if ptype != 1:  # Not title
                    indices.append(i)
            except Exception:
                # Not a placeholder, include it
                indices.append(i)
        return indices

    if target.replace(",", "").replace(" ", "").isdigit():
        # Specific shape IDs — need to find by shape ID, not index
        target_ids = {int(x.strip()) for x in target.split(",")}
        for i in range(1, total + 1):
            shape = slide.Shapes(i)
            try:
                if shape.Id in target_ids:
                    indices.append(i)
            except Exception:
                pass
        return indices

    # Name match
    target_lower = target.lower()
    for i in range(1, total + 1):
        shape = slide.Shapes(i)
        try:
            if target_lower in shape.Name.lower():
                indices.append(i)
        except Exception:
            pass

    return indices
