"""
PPT Animation Engine — 专业级 PPTX 动画注入引擎
=================================================
通过 Office Open XML 直接操作，为 PPTX 幻灯片添加原生动画效果。
支持 40+ 种动画效果，逐元素编排，精确定时控制。

用法:
    from animate_ppt_engine import add_animations
    result = add_animations("input.pptx", animations, output="output.pptx")
"""

from __future__ import annotations

import copy
import logging
import os
import shutil
import tempfile
import zipfile
from typing import Optional
from lxml import etree

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# XML NAMESPACES (Office Open XML PresentationML)
# ═══════════════════════════════════════════════════════════════════════════

NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# ═══════════════════════════════════════════════════════════════════════════
# ANIMATION EFFECT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

# Maps user-friendly names → (presetClass, presetSubtype, presetId, transitionType)
# These correspond to Office's native animation presets.

ENTRANCE_EFFECTS = {
    "appear":           ("entr", 0, 10, None),
    "fade":             ("entr", 1, 10, "fade"),
    "fly_in":           ("entr", 2, 2, "push"),
    "wipe":             ("entr", 1, 22, "wipe"),
    "zoom":             ("entr", 1, 53, "zoom"),
    "float_up":         ("entr", 2, 29, "push"),
    "float_down":       ("entr", 4, 29, "push"),
    "float_left":       ("entr", 8, 29, "push"),
    "float_right":      ("entr", 16, 29, "push"),
    "split_vertical":   ("entr", 1, 17, "split"),
    "split_horizontal": ("entr", 2, 17, "split"),
    "blinds_horizontal":("entr", 1, 3, "blinds"),
    "blinds_vertical":  ("entr", 2, 3, "blinds"),
    "checkerboard":     ("entr", 1, 4, "checkerboard"),
    "circle":           ("entr", 1, 5, "circle"),
    "diamond":          ("entr", 1, 6, "diamond"),
    "plus":             ("entr", 1, 18, "plus"),
    "dissolve":         ("entr", 1, 7, "dissolve"),
    "random_bars":      ("entr", 1, 9, "random"),
    "peek_up":          ("entr", 2, 19, "uncover"),
    "peek_down":        ("entr", 4, 19, "uncover"),
    "peek_left":        ("entr", 8, 19, "uncover"),
    "peek_right":       ("entr", 16, 19, "uncover"),
    "grow_turn":        ("entr", 1, 28, "growAndTurn"),
    "swivel":           ("entr", 1, 30, "pull"),
    "expand":           ("entr", 1, 54, "pull"),
    "spin":             ("entr", 1, 55, "pull"),
    "rise_up":          ("entr", 1, 57, "pull"),
    "bouncy":           ("entr", 1, 58, "pull"),
    "center_rotate":    ("entr", 1, 60, "pull"),
    "collapse":         ("entr", 1, 61, "pull"),
    "stretch":          ("entr", 1, 62, "pull"),
    "whip":             ("entr", 1, 63, "pull"),
    "compress":         ("entr", 1, 64, "pull"),
    "thread":           ("entr", 1, 65, "pull"),
}

EXIT_EFFECTS = {
    "disappear":        ("exit", 0, 10, None),
    "fade_out":         ("exit", 1, 10, "fade"),
    "fly_out":          ("exit", 2, 2, "push"),
    "wipe_out":         ("exit", 1, 22, "wipe"),
    "zoom_out":         ("exit", 1, 53, "zoom"),
    "float_down_exit":  ("exit", 4, 29, "push"),
    "float_up_exit":    ("exit", 2, 29, "push"),
    "split_out_v":      ("exit", 1, 17, "split"),
    "split_out_h":      ("exit", 2, 17, "split"),
    "blinds_out_h":     ("exit", 1, 3, "blinds"),
    "blinds_out_v":     ("exit", 2, 3, "blinds"),
    "dissolve_out":     ("exit", 1, 7, "dissolve"),
    "random_bars_out":  ("exit", 1, 9, "random"),
    "collapse_exit":    ("exit", 1, 61, "pull"),
    "spin_exit":        ("exit", 1, 55, "pull"),
}

EMPHASIS_EFFECTS = {
    "pulse":            ("emph", 1, 22, None),
    "color_pulse":      ("emph", 1, 2, None),
    "grow":             ("emph", 1, 19, None),
    "shrink":           ("emph", 2, 19, None),
    "spin_cw":          ("emph", 1, 30, None),
    "spin_ccw":         ("emph", 2, 30, None),
    "transparency":     ("emph", 1, 32, None),
    "bold_reveal":      ("emph", 1, 34, None),
    "underline_reveal": ("emph", 1, 35, None),
    "desaturate":       ("emph", 1, 36, None),
    "darken":           ("emph", 1, 37, None),
    "lighten":          ("emph", 2, 37, None),
    "brush_on_color":   ("emph", 1, 39, None),
    "grow_color":       ("emph", 1, 44, None),
}

# All effects combined
ALL_EFFECTS = {**ENTRANCE_EFFECTS, **EXIT_EFFECTS, **EMPHASIS_EFFECTS}

# Effect category keywords for auto-detection
_ENTRANCE_KEYWORDS = {"appear", "fade", "fly", "wipe", "zoom", "float", "split",
                      "blinds", "checkerboard", "circle", "diamond", "plus",
                      "dissolve", "random", "peek", "grow", "swivel", "expand",
                      "spin", "rise", "bouncy", "center", "collapse", "stretch",
                      "whip", "compress", "thread"}
_EXIT_KEYWORDS = {"disappear", "exit", "out", "fade_out", "fly_out", "wipe_out"}


def _detect_category(effect_name: str) -> str:
    """Detect if an effect is entrance, exit, or emphasis."""
    lower = effect_name.lower()
    if lower in EXIT_EFFECTS or "_out" in lower or "exit" in lower:
        return "exit"
    if lower in EMPHASIS_EFFECTS:
        return "emphasis"
    return "entrance"


# ═══════════════════════════════════════════════════════════════════════════
# SLIDE TRANSITION DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

TRANSITION_TYPES = {
    "fade":             "p:fade",
    "push":             "p:push",
    "wipe":             "p:wipe",
    "split":            "p:split",
    "blinds":           "p:blinds",
    "checkerboard":     "p:checker",
    "circle":           "p:circle",
    "diamond":          "p:diamond",
    "dissolve":         "p:dissolve",
    "cover":            "p:cover",
    "uncover":          "p:pull",
    "random":           "p:random",
    "zoom":             "p:zoom",
    "grow_and_turn":    "p:pull",
    "flip":             "p:pull",
    "gallery":          "p:gallery",
    "convey":           "p:convey",
    "rotate":           "p:rotate",
    "cube":             "p:cube",
    "box":              "p:box",
    "pan":              "p:pan",
    "glitter":          "p:glitter",
    "honeycomb":        "p:honeycomb",
    "random_bar":       "p:randomBar",
    "shred":            "p:shred",
    "wind":             "p:wind",
    "morph":            "p:prstTransition",
}


# ═══════════════════════════════════════════════════════════════════════════
# XML BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _ns(tag: str, ns: str = P) -> str:
    """Create a namespaced tag: {namespace}tag"""
    return f"{{{ns}}}{tag}"


def _build_effect_element(effect_name: str, shape_id: int, tn_node_id: int,
                           delay_ms: int = 0, duration_ms: int = 500,
                           trigger: str = "onclick") -> etree._Element:
    """Build a p:effect XML element for a single shape animation.
    
    Args:
        effect_name: Effect key from ALL_EFFECTS
        shape_id: The spId of the shape to animate
        tn_node_id: Unique timing node ID
        delay_ms: Delay before animation starts (ms)
        duration_ms: Duration of animation (ms)
        trigger: "onclick", "withprev", "afterprev"
    """
    effect_info = ALL_EFFECTS.get(effect_name.lower().replace("-", "_").replace(" ", "_"))
    if not effect_info:
        raise ValueError(f"Unknown effect: {effect_name}. Available: {sorted(ALL_EFFECTS.keys())}")

    preset_class, preset_sub, preset_id, _ = effect_info
    category = _detect_category(effect_name)

    # Convert ms to EMUs (1ms = 1000 in Office timing)
    dur_val = duration_ms * 1000
    delay_val = delay_ms * 1000

    # Build trigger type
    if trigger == "withprev":
        node_type = "withEffect"
        grp_id_start = tn_node_id
    elif trigger == "afterprev":
        node_type = "afterEffect"
        grp_id_start = tn_node_id
    else:  # onclick
        node_type = "clickEffect"
        grp_id_start = tn_node_id

    # Build the effect element XML string
    xml = f'''<p:effect xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"
        id="{tn_node_id}" presetClass="{preset_class}" presetSubtype="{preset_sub}"
        transition="in" pNodeType="{node_type}">
      <p:cBhvr>
        <p:cTn id="{tn_node_id + 1}" dur="{dur_val}" fill="hold">
          <p:stCondLst>
            <p:cond delay="{delay_val}"/>
          </p:stCondLst>
        </p:cTn>
        <p:tgtEl>
          <p:spTgt spid="{shape_id}"/>
        </p:tgtEl>
      </p:cBhvr>
      <p:template xmlns:p="{P}" xmlns:a="{A}" effectId="{preset_id}">
        <p:tnLst>
          <p:set>
            <p:cBhvr>
              <p:cTn id="{tn_node_id + 2}" dur="{dur_val}" fill="hold">
                <p:stCondLst>
                  <p:cond delay="{delay_val}"/>
                </p:stCondLst>
              </p:cTn>
              <p:tgtEl>
                <p:spTgt spid="{shape_id}"/>
              </p:tgtEl>
              <p:attrNameLst>
                <p:attrName>style.visibility</p:attrName>
              </p:attrNameLst>
            </p:cBhvr>
            <p:to>
              <p:strVal val="visible"/>
            </p:to>
          </p:set>
        </p:tnLst>
      </p:template>
    </p:effect>'''

    return etree.fromstring(xml.encode("utf-8"))


def _build_timing_tree(animations: list[etree._Element], next_id: int) -> etree._Element:
    """Build the complete p:timing XML element containing all animations.
    
    Args:
        animations: List of p:effect elements
        next_id: Next available timing node ID
    """
    timing = etree.Element(_ns("timing"))

    # Build the main sequence
    tn_lst = etree.SubElement(timing, _ns("tnLst"))
    par = etree.SubElement(tn_lst, _ns("par"))
    c_tn_par = etree.SubElement(par, _ns("cTn"), attrib={
        "id": str(next_id),
        "dur": "indefinite",
        "restart": "never",
        "nodeType": "tmRoot",
    })
    child_tn_lst = etree.SubElement(c_tn_par, _ns("childTnLst"))

    # Main sequence node
    seq = etree.SubElement(child_tn_lst, _ns("seq"), attrib={
        "concurrent": "1",
        "nextAc": "seek",
    })
    seq_c_tn = etree.SubElement(seq, _ns("cTn"), attrib={
        "id": str(next_id + 1),
        "dur": "indefinite",
        "nodeType": "mainSeq",
    })
    seq_child = etree.SubElement(seq_c_tn, _ns("childTnLst"))

    # Add each animation to the sequence
    for i, anim in enumerate(animations):
        par_elem = etree.SubElement(seq_child, _ns("par"))
        par_c_tn = etree.SubElement(par_elem, _ns("cTn"), attrib={
            "id": str(next_id + 2 + i * 10),
            "fill": "hold",
        })
        par_child = etree.SubElement(par_c_tn, _ns("childTnLst"))
        par_child.append(anim)
        next_id += 10  # Leave room for nested IDs

    # Previous conditions list for the sequence
    prev_cond_lst = etree.SubElement(seq, _ns("prevCondLst"))
    prev_cond = etree.SubElement(prev_cond_lst, _ns("cond"))
    prev_cond_tgt = etree.SubElement(prev_cond, _ns("tgtEl"))
    etree.SubElement(prev_cond_tgt, _ns("sldTgt"))
    prev_cond.set("evt", "onPrev")
    prev_cond.set("delay", "0")

    # Next conditions list
    next_cond_lst = etree.SubElement(seq, _ns("nextCondLst"))
    next_cond = etree.SubElement(next_cond_lst, _ns("cond"))
    next_cond_tgt = etree.SubElement(next_cond, _ns("tgtEl"))
    etree.SubElement(next_cond_tgt, _ns("sldTgt"))
    next_cond.set("evt", "onNext")
    next_cond.set("delay", "0")

    return timing


def _build_slide_transition(transition_type: str, duration_sec: float = 1.0,
                             advance_click: bool = True,
                             advance_after_sec: Optional[float] = None,
                             direction: Optional[str] = None) -> etree._Element:
    """Build p:transition XML element for slide transitions.
    
    Args:
        transition_type: Key from TRANSITION_TYPES
        duration_sec: Transition duration in seconds
        advance_click: Whether click advances the slide
        advance_after_sec: Auto-advance after N seconds (None = manual only)
        direction: "up", "down", "left", "right" for directional transitions
    """
    trans_tag = TRANSITION_TYPES.get(transition_type.lower().replace("-", "_"))
    if not trans_tag:
        raise ValueError(f"Unknown transition: {transition_type}. Available: {sorted(TRANSITION_TYPES.keys())}")

    # Convert seconds to ms string
    spd = "med"
    if duration_sec < 0.5:
        spd = "fast"
    elif duration_sec > 1.5:
        spd = "slow"

    transition = etree.Element(_ns("transition"), attrib={
        "spd": spd,
        "advClick": "1" if advance_click else "0",
    })

    if advance_after_sec is not None:
        transition.set("advTm", str(int(advance_after_sec * 1000)))

    # Add the specific transition element
    # Parse the tag to get namespace and local name
    tag_parts = trans_tag.split(":")
    if len(tag_parts) == 2:
        ns_prefix, local = tag_parts
        ns_uri = NSMAP.get(ns_prefix, P)
        trans_elem = etree.SubElement(transition, f"{{{ns_uri}}}{local}")
    else:
        trans_elem = etree.SubElement(transition, _ns(trans_tag))

    if direction:
        dir_map = {"up": "u", "down": "d", "left": "l", "right": "r",
                   "horizontal": "horz", "vertical": "vert"}
        dir_val = dir_map.get(direction.lower(), direction)
        trans_elem.set("dir", dir_val)

    return transition


# ═══════════════════════════════════════════════════════════════════════════
# SLIDE PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

def _get_shape_ids(slide_tree: etree._ElementTree) -> dict[str, int]:
    """Extract all shape IDs from a slide. Returns {name: spId}."""
    shapes = {}
    for sp in slide_tree.iter(_ns("sp")):
        sp_id_elem = sp.find(f".//{_ns('cNvPr')}")
        if sp_id_elem is not None:
            sp_id = sp_id_elem.get("id")
            sp_name = sp_id_elem.get("name", f"Shape_{sp_id}")
            if sp_id:
                shapes[sp_name] = int(sp_id)
    # Also handle pictures
    for pic in slide_tree.iter(f"{{{P}}}pic"):
        nv_pr = pic.find(f".//{_ns('cNvPr')}")
        if nv_pr is not None:
            sp_id = nv_pr.get("id")
            sp_name = nv_pr.get("name", f"Pic_{sp_id}")
            if sp_id:
                shapes[sp_name] = int(sp_id)
    # Also handle group shapes
    for grp in slide_tree.iter(f"{{{P}}}grpSp"):
        nv_pr = grp.find(f".//{_ns('cNvPr')}")
        if nv_pr is not None:
            sp_id = nv_pr.get("id")
            sp_name = nv_pr.get("name", f"Grp_{sp_id}")
            if sp_id:
                shapes[sp_name] = int(sp_id)
    # Also handle graphic frames and ole objects
    for frame in slide_tree.iter(f"{{{P}}}graphicFrame"):
        nv_pr = frame.find(f".//{_ns('cNvPr')}")
        if nv_pr is not None:
            sp_id = nv_pr.get("id")
            sp_name = nv_pr.get("name", f"Chart_{sp_id}")
            if sp_id:
                shapes[sp_name] = int(sp_id)
    return shapes


def _select_shapes(shapes: dict[str, int], target: str) -> list[tuple[str, int]]:
    """Select shapes based on target specification.
    
    target options:
        "all" — all shapes
        "all_text" — text boxes and shapes with text
        "all_images" — pictures
        "all_charts" — charts/graphs
        "title" — title shapes
        "body" — body text shapes (non-title)
        "1,3,5" — specific shape IDs
        "TextBox 1" — specific shape name (partial match)
    """
    if target == "all":
        return list(shapes.items())

    selected = []

    if target == "all_text":
        for name, sid in shapes.items():
            name_lower = name.lower()
            if any(kw in name_lower for kw in ["text", "title", "subtitle", "body", "placeholder"]):
                selected.append((name, sid))
        if not selected:  # Fallback: select all shapes
            selected = list(shapes.items())

    elif target == "all_images":
        for name, sid in shapes.items():
            if any(kw in name.lower() for kw in ["pic", "image", "photo", "picture"]):
                selected.append((name, sid))

    elif target == "all_charts":
        for name, sid in shapes.items():
            if any(kw in name.lower() for kw in ["chart", "graph", "table"]):
                selected.append((name, sid))

    elif target == "title":
        for name, sid in shapes.items():
            if "title" in name.lower() or "Title" in name:
                selected.append((name, sid))

    elif target == "body":
        for name, sid in shapes.items():
            if "title" not in name.lower() and "Title" not in name:
                selected.append((name, sid))

    elif target.replace(",", "").replace(" ", "").isdigit():
        # Specific IDs: "1,3,5"
        target_ids = {int(x.strip()) for x in target.split(",")}
        for name, sid in shapes.items():
            if sid in target_ids:
                selected.append((name, sid))

    else:
        # Partial name match
        target_lower = target.lower()
        for name, sid in shapes.items():
            if target_lower in name.lower():
                selected.append((name, sid))

    return selected


def _get_max_tn_id(slide_tree: etree._ElementTree) -> int:
    """Find the maximum timing node ID in a slide to avoid conflicts."""
    max_id = 0
    for elem in slide_tree.iter():
        for attr in ["id"]:
            val = elem.get(attr)
            if val and val.isdigit():
                max_id = max(max_id, int(val))
    # Also check for spId
    for elem in slide_tree.iter():
        for attr in ["spid"]:
            val = elem.get(attr)
            if val and val.isdigit():
                max_id = max(max_id, int(val))
    return max(max_id + 100, 1000)  # Start well above existing IDs


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def list_effects() -> dict[str, list[str]]:
    """List all available animation effects, grouped by category."""
    return {
        "entrance": sorted(ENTRANCE_EFFECTS.keys()),
        "exit": sorted(EXIT_EFFECTS.keys()),
        "emphasis": sorted(EMPHASIS_EFFECTS.keys()),
        "transitions": sorted(TRANSITION_TYPES.keys()),
    }


def list_shapes(pptx_path: str, slide_number: Optional[int] = None) -> dict:
    """List all shapes in a PPTX file.
    
    Args:
        pptx_path: Path to PPTX file
        slide_number: Specific slide (1-indexed), or None for all slides
    
    Returns:
        Dict of {slide_number: {shape_name: shape_id, ...}}
    """
    result = {}
    with zipfile.ZipFile(pptx_path, "r") as zf:
        slide_files = sorted([f for f in zf.namelist()
                              if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
        for idx, slide_file in enumerate(slide_files, 1):
            if slide_number and idx != slide_number:
                continue
            xml_data = zf.read(slide_file)
            tree = etree.ElementTree(etree.fromstring(xml_data))
            shapes = _get_shape_ids(tree)
            if shapes:
                result[idx] = shapes
    return result


def add_animations(
    pptx_path: str,
    animations: list[dict],
    output: Optional[str] = None,
    transitions: Optional[list[dict]] = None,
) -> dict:
    """Add animations to a PPTX file.
    
    Args:
        pptx_path: Path to input PPTX file
        animations: List of animation specs, each dict has:
            - "slide": int — slide number (1-indexed)
            - "effect": str — effect name (e.g., "fade", "fly_in", "appear")
            - "target": str — what to animate ("all", "all_text", "title", "1,3,5", etc.)
            - "duration": float — duration in seconds (default 0.5)
            - "delay": float — delay in seconds (default 0)
            - "trigger": str — "onclick", "withprev", "afterprev" (default "afterprev")
        output: Output file path (default: input_anim.pptx)
        transitions: Optional list of slide transition specs:
            - "slide": int — slide number
            - "type": str — transition type (e.g., "fade", "push", "wipe")
            - "duration": float — duration in seconds
            - "direction": str — "up", "down", "left", "right"
    
    Returns:
        {"success": True, "path": output_path, "slides_animated": int, "shapes_animated": int}
    """
    if not os.path.isfile(pptx_path):
        return {"error": f"File not found: {pptx_path}", "success": False}

    if not output:
        base, ext = os.path.splitext(pptx_path)
        output = f"{base}_animated{ext}"

    # ── Dual engine: COM first on Windows, XML fallback ──
    import sys
    if sys.platform == "win32":
        try:
            from .animate_ppt_com import add_animations_com, is_com_available
            if is_com_available():
                _log.info("Using COM backend (PowerPoint automation)")
                result = add_animations_com(pptx_path, animations, output=output, transitions=transitions)
                com_failures = result.get("shapes_failed", 0) + result.get("transitions_failed", 0)
                if result.get("success") and result.get("shapes_animated", 0) > 0 and com_failures == 0:
                    return result
                _log.warning("COM backend: animated=%d, failed=%d (shapes_failed=%d, transitions_failed=%d) — falling back to XML",
                             result.get("shapes_animated", 0), com_failures,
                             result.get("shapes_failed", 0), result.get("transitions_failed", 0))
        except Exception as e:
            _log.warning("COM backend unavailable (%s), using XML", e)

    # ── XML injection backend ──
    _log.info("Using XML injection backend")
    # Handle file lock: if source is locked (e.g. by PowerPoint), retry with backoff
    for _attempt in range(3):
        try:
            shutil.copy2(pptx_path, output)
            break
        except PermissionError:
            if _attempt < 2:
                import time
                _log.warning("File locked, retrying in 1s (attempt %d/3)", _attempt + 1)
                time.sleep(1)
            else:
                raise

    # Build transition index: {slide_num: transition_element}
    trans_index = {}
    if transitions:
        for t in transitions:
            slide_num = t.get("slide", 1)
            trans_type = t.get("type", "fade")
            duration = t.get("duration", 1.0)
            direction = t.get("direction")
            try:
                trans_elem = _build_slide_transition(trans_type, duration, direction=direction)
                trans_index[slide_num] = trans_elem
            except ValueError as e:
                _log.warning("Skipping transition for slide %d: %s", slide_num, e)

    # Group animations by slide
    anims_by_slide: dict[int, list[dict]] = {}
    for anim in animations:
        slide_num = anim.get("slide", 1)
        if slide_num not in anims_by_slide:
            anims_by_slide[slide_num] = []
        anims_by_slide[slide_num].append(anim)

    slides_animated = 0
    shapes_animated = 0

    # Process the PPTX (zip file)
    tmp_dir = tempfile.mkdtemp()
    try:
        # Extract
        with zipfile.ZipFile(output, "r") as zf:
            zf.extractall(tmp_dir)

        # Process each slide that has animations
        for slide_num in sorted(set(list(anims_by_slide.keys()) + list(trans_index.keys()))):
            slide_file = os.path.join(tmp_dir, f"ppt/slides/slide{slide_num}.xml")
            if not os.path.isfile(slide_file):
                _log.warning("Slide %d not found, skipping", slide_num)
                continue

            # Parse slide XML
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(slide_file, parser)
            root = tree.getroot()

            # Get shapes on this slide
            shapes = _get_shape_ids(tree)
            if not shapes:
                _log.warning("No shapes found on slide %d", slide_num)
                continue

            # Build animation elements
            effect_elements = []
            next_id = _get_max_tn_id(tree)

            slide_anims = anims_by_slide.get(slide_num, [])
            for anim_spec in slide_anims:
                effect_name = anim_spec.get("effect", "fade")
                target = anim_spec.get("target", "all_text")
                duration = anim_spec.get("duration", 0.5)
                delay = anim_spec.get("delay", 0)
                trigger = anim_spec.get("trigger", "afterprev")

                # Select shapes
                selected = _select_shapes(shapes, target)
                if not selected:
                    _log.warning("No shapes matched target '%s' on slide %d", target, slide_num)
                    continue

                # Create animation for each selected shape
                for i, (shape_name, shape_id) in enumerate(selected):
                    shape_delay = delay + (i * 0.1)  # Stagger by 100ms per element
                    try:
                        effect_elem = _build_effect_element(
                            effect_name, shape_id, next_id,
                            delay_ms=int(shape_delay * 1000),
                            duration_ms=int(duration * 1000),
                            trigger=trigger,
                        )
                        effect_elements.append(effect_elem)
                        shapes_animated += 1
                        next_id += 10
                    except ValueError as e:
                        _log.warning("Skipping effect for shape '%s': %s", shape_name, e)

            # Inject animations into slide XML
            if effect_elements:
                c_sld = root.find(_ns("cSld"))
                if c_sld is None:
                    _log.warning("No cSld found in slide %d", slide_num)
                    continue

                # Remove existing timing AND bldLst if present
                existing_timing = c_sld.find(_ns("timing"))
                if existing_timing is not None:
                    c_sld.remove(existing_timing)
                existing_bld = c_sld.find(_ns("bldLst"))
                if existing_bld is not None:
                    c_sld.remove(existing_bld)

                # Build and inject new timing tree
                timing = _build_timing_tree(effect_elements, next_id + 100)
                c_sld.append(timing)

                # Add bldLst (build list) for paragraph-level animation compatibility
                # Without this, PowerPoint cannot add paragraph animations to shapes
                # that already have animations — it causes file corruption
                bld_lst = etree.SubElement(c_sld, _ns("bldLst"))
                for anim_spec in slide_anims:
                    target = anim_spec.get("target", "all_text")
                    selected = _select_shapes(shapes, target)
                    for shape_name, shape_id in selected:
                        bld_p = etree.SubElement(bld_lst, _ns("bldP"))
                        bld_p.set("spid", str(shape_id))
                        bld_p.set("grpId", "0")
                        bld_p.set("bld", "anim")
                        bld_p.set("animBg", "1")

                slides_animated += 1

            # Inject slide transition
            if slide_num in trans_index:
                existing_trans = root.find(_ns("transition"))
                if existing_trans is not None:
                    root.remove(existing_trans)
                root.append(trans_index[slide_num])

            # Write back
            tree.write(slide_file, xml_declaration=True, encoding="UTF-8", standalone=True)

        # Repack the zip — preserve original structure, only overwrite modified slides
        _repack_pptx(output, tmp_dir)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "success": True,
        "path": output,
        "slides_animated": slides_animated,
        "shapes_animated": shapes_animated,
    }


def _repack_pptx(output: str, tmp_dir: str) -> None:
    """Repack extracted PPTX directory into a valid .pptx ZIP.
    
    Key fix: preserve ZIP entry order from [Content_Types].xml and 
    use consistent compression to prevent PowerPoint from detecting 
    the file as "needs repair".
    """
    import io
    
    # Build list of files to pack, with [Content_Types].xml first (OOXML spec requirement)
    files_to_pack = []
    content_types_path = os.path.join(tmp_dir, "[Content_Types].xml")
    if os.path.isfile(content_types_path):
        files_to_pack.append(("[Content_Types].xml", content_types_path))
    
    # _rels/.rels should be second
    rels_path = os.path.join(tmp_dir, "_rels", ".rels")
    if os.path.isfile(rels_path):
        files_to_pack.append(("_rels/.rels", rels_path))
    
    # Then all other files in sorted order
    for dirpath, dirnames, filenames in os.walk(tmp_dir):
        dirnames.sort()  # Ensure consistent directory traversal
        for filename in sorted(filenames):
            file_path = os.path.join(dirpath, filename)
            arcname = os.path.relpath(file_path, tmp_dir).replace("\\", "/")
            # Skip already-added special files
            if arcname in ("[Content_Types].xml", "_rels/.rels"):
                continue
            files_to_pack.append((arcname, file_path))
    
    # Write zip with consistent settings
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for arcname, file_path in files_to_pack:
            with open(file_path, "rb") as f:
                data = f.read()
            zf.writestr(arcname, data)


def add_slide_transitions(
    pptx_path: str,
    transition_type: str = "fade",
    duration_sec: float = 1.0,
    direction: Optional[str] = None,
    slides: Optional[list[int]] = None,
    output: Optional[str] = None,
) -> dict:
    """Add slide transitions to all or specific slides.
    
    Args:
        pptx_path: Path to input PPTX file
        transition_type: Type of transition (e.g., "fade", "push", "wipe")
        duration_sec: Duration in seconds
        direction: "up", "down", "left", "right"
        slides: List of slide numbers (None = all slides)
        output: Output file path
    
    Returns:
        {"success": True, "path": output, "slides_transitioned": int}
    """
    if not os.path.isfile(pptx_path):
        return {"error": f"File not found: {pptx_path}", "success": False}

    if not output:
        base, ext = os.path.splitext(pptx_path)
        output = f"{base}_transitions{ext}"

    shutil.copy2(pptx_path, output)

    tmp_dir = tempfile.mkdtemp()
    slides_transitioned = 0
    try:
        with zipfile.ZipFile(output, "r") as zf:
            zf.extractall(tmp_dir)

        slide_files = sorted([f for f in os.listdir(os.path.join(tmp_dir, "ppt/slides"))
                              if f.startswith("slide") and f.endswith(".xml")])

        for idx, slide_file in enumerate(slide_files, 1):
            if slides and idx not in slides:
                continue

            slide_path = os.path.join(tmp_dir, "ppt/slides", slide_file)
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(slide_path, parser)
            root = tree.getroot()

            # Remove existing transition
            existing = root.find(_ns("transition"))
            if existing is not None:
                root.remove(existing)

            # Add new transition
            trans_elem = _build_slide_transition(transition_type, duration_sec, direction=direction)
            root.append(trans_elem)

            tree.write(slide_path, xml_declaration=True, encoding="UTF-8", standalone=True)
            slides_transitioned += 1

        _repack_pptx(output, tmp_dir)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "success": True,
        "path": output,
        "slides_transitioned": slides_transitioned,
    }
