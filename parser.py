import os
import json
import fitz  # PyMuPDF

def is_white(color):
    """Checks if a color (tuple/list of 3 floats) represents white or near-white."""
    if color is None:
        return False
    return all(c > 0.95 for c in color)

def serialize_rect(rect):
    """Converts a fitz.Rect object to a standard list [x0, y0, x1, y1]."""
    return [rect.x0, rect.y0, rect.x1, rect.y1]

def serialize_point(point):
    """Converts a fitz.Point object to a standard list [x, y]."""
    return [point.x, point.y]

def serialize_quad(quad):
    """Converts a fitz.Quad object to a list of lists representing 4 corners."""
    return [
        [quad.ul.x, quad.ul.y],
        [quad.ur.x, quad.ur.y],
        [quad.lr.x, quad.lr.y],
        [quad.ll.x, quad.ll.y]
    ]

def is_effectively_closed(path):
    """Checks if a PyMuPDF drawing path is closed explicitly or is closed implicitly by returning to start coordinate."""
    if path.get("closePath", False):
        return True
    items = path.get("items", [])
    if not items:
        return False
    
    first_item = items[0]
    last_item = items[-1]
    
    # Rects and Quads are closed by definition
    if first_item[0] in ["re", "qu"] or last_item[0] in ["re", "qu"]:
        return True
        
    first_pt = None
    last_pt = None
    
    if first_item[0] in ["l", "c"]:
        first_pt = first_item[1]
    if last_item[0] == "l":
        last_pt = last_item[2]
    elif last_item[0] == "c":
        last_pt = last_item[4]
        
    if first_pt and last_pt:
        # Distance calculation between first point start and last point end
        dist = ((first_pt.x - last_pt.x)**2 + (first_pt.y - last_pt.y)**2)**0.5
        return dist < 1.5
    return False

def find_arrowhead_in_items(items):
    """
    Scans drawing items to find any sub-sequence of lines that forms a small closed triangle (an arrowhead).
    Returns the coordinates of the arrowhead triangle if found, else None.
    """
    for i in range(len(items) - 2):
        item1 = items[i]
        item2 = items[i+1]
        item3 = items[i+2]
        
        # Check if they are all lines
        if item1[0] == "l" and item2[0] == "l" and item3[0] == "l":
            p1_start, p1_end = item1[1], item1[2]
            p2_start, p2_end = item2[1], item2[2]
            p3_start, p3_end = item3[1], item3[2]
            
            # Check if they form a closed loop:
            # p1_end == p2_start
            # p2_end == p3_start
            # p3_end == p1_start
            # (allowing minor float discrepancies < 0.8)
            def close_enough(pt1, pt2):
                return ((pt1.x - pt2.x)**2 + (pt1.y - pt2.y)**2)**0.5 < 0.8
                
            if close_enough(p1_end, p2_start) and close_enough(p2_end, p3_start) and close_enough(p3_end, p1_start):
                # Calculate size of this triangle
                xs = [p1_start.x, p1_end.x, p3_start.x]
                ys = [p1_start.y, p1_end.y, p3_start.y]
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                if w < 16 and h < 16:
                    return {
                        "vertices": [[p1_start.x, p1_start.y], [p2_start.x, p2_start.y], [p3_start.x, p3_start.y]],
                        "bbox": [min(xs), min(ys), max(xs), max(ys)]
                    }
    return None

def classify_shape_raw(path):
    """
    Classifies a raw PyMuPDF drawing path into a flowchart shape category:
    'decision_box' (diamond), 'process_box' (rectangle), 'start_end_terminal' (oval/rounded rect), 
    'arrow_shaft' (connector line), 'arrow_head' (small filled pointer), or 'other'.
    """
    items = path.get("items", [])
    if not items:
        return "other"
        
    rect = path.get("rect")
    if not rect:
        return "other"
        
    w = rect.x1 - rect.x0
    h = rect.y1 - rect.y0
    
    close_path = is_effectively_closed(path)
    
    # Ignore noise or shapes with extremely small dimensions
    if not close_path:
        # Open paths (connector lines/shafts) can have height/width < 5, only ignore if both are tiny
        if w < 5 and h < 5:
            return "other"
    else:
        # Closed shapes (boxes) must have both dimensions >= 5
        if w < 5 or h < 5:
            return "other"
            
    # Check if this path contains an arrowhead. If so, it is an arrow (shaft + head).
    if find_arrowhead_in_items(items):
        return "arrow"
        
    has_curves = any(item[0] == "c" for item in items)
    has_rect = any(item[0] == "re" for item in items)
    line_items = [item for item in items if item[0] == "l"]
    line_count = len(line_items)
    
    has_fill = path.get("fill") is not None
    
    # Heuristics:
    # 1. Arrow Heads (Small filled polygons)
    if close_path and has_fill and w < 16 and h < 16:
        return "arrow_head"
        
    # 2. Start / End points (Terminals)
    # Typically closed curves or rounded rectangles
    if has_curves and close_path:
        return "start_end_terminal"
        
    # 3. Process boxes (Rectangles)
    if has_rect and close_path:
        return "process_box"
        
    # 4. Decision boxes (Diamonds)
    # Closed path of 4 lines, not axis-aligned
    if line_count == 4 and close_path:
        is_axis_aligned = False
        for item in line_items:
            p1, p2 = item[1], item[2]
            if abs(p1.x - p2.x) < 0.5 or abs(p1.y - p2.y) < 0.5:
                is_axis_aligned = True
                break
        if not is_axis_aligned:
            return "decision_box"
        else:
            return "process_box"
            
    # Default closed path of 4 lines is a process box
    if line_count == 4 and close_path:
        return "process_box"
        
    # 5. Arrows / Connection lines (Open paths)
    if not close_path:
        return "arrow_shaft"
        
    return "other"

def serialize_drawing(path, text_dict=None):
    """
    Translates a PyMuPDF drawing path dictionary to a clean, JSON-serializable dictionary.
    This hardcodes the translation of PyMuPDF drawing commands (type: 're', 'l', 'c', 'qu') 
    and geometries (Rect, Point, Quad) to standard primitive types.
    """
    serialized = {}
    
    # Check if there is an arrowhead triangle inside the items
    arrowhead = find_arrowhead_in_items(path.get("items", []))
    if arrowhead:
        serialized["arrowhead"] = arrowhead
        serialized["classification"] = "arrow"
    else:
        serialized["classification"] = classify_shape_raw(path)
        
    # Map text inside block shapes
    classification = serialized["classification"]
    if text_dict and classification in ["process_box", "decision_box", "start_end_terminal"] and "rect" in path:
        rect = path["rect"]
        rect_tuple = (rect.x0, rect.y0, rect.x1, rect.y1)
        serialized["text"] = extract_text_in_rect(rect_tuple, text_dict)
    else:
        serialized["text"] = ""
    
    # 1. Translate draw commands/items list
    serialized_items = []
    for item in path.get("items", []):
        command = item[0]
        if command == "re":  # Rectangle
            serialized_items.append({
                "type": "rect",
                "bbox": serialize_rect(item[1])
            })
        elif command == "l":  # Line
            serialized_items.append({
                "type": "line",
                "p1": serialize_point(item[1]),
                "p2": serialize_point(item[2])
            })
        elif command == "c":  # Cubic Bezier Curve
            serialized_items.append({
                "type": "curve",
                "p1": serialize_point(item[1]),
                "p2": serialize_point(item[2]),
                "p3": serialize_point(item[3]),
                "p4": serialize_point(item[4])
            })
        elif command == "qu":  # Quad
            serialized_items.append({
                "type": "quad",
                "points": serialize_quad(item[1])
            })
            
    serialized["items"] = serialized_items
    
    # 2. Serialize basic metadata/style properties
    serialized["type"] = path.get("type", "")
    if "rect" in path:
        serialized["rect"] = serialize_rect(path["rect"])
    
    # Convert colors (which are float RGB tuples) to standard lists
    serialized["color"] = list(path["color"]) if path.get("color") is not None else None
    serialized["fill"] = list(path["fill"]) if path.get("fill") is not None else None
    
    serialized["width"] = path.get("width", 1.0)
    serialized["lineCap"] = path.get("lineCap", 0)
    serialized["lineJoin"] = path.get("lineJoin", 0)
    serialized["closePath"] = path.get("closePath", False)
    serialized["dashes"] = path.get("dashes", "[]")
    serialized["seqno"] = path.get("seqno", 0)
    serialized["layer"] = path.get("layer", None)
    
    return serialized

def make_serializable(obj):
    """Recursively converts any python object into standard JSON-serializable types."""
    if isinstance(obj, dict):
        return {str(k): make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [make_serializable(v) for v in obj]
    elif isinstance(obj, bytes):
        return f"<bytes: {len(obj)} bytes>"
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    else:
        try:
            return str(obj)
        except:
            return None

def extract_text_in_rect(rect, text_dict):
    """
    Finds and joins all text spans in text_dict whose bounding box centers
    fall inside the given rect coordinates [x0, y0, x1, y1].
    """
    sx0, sy0, sx1, sy1 = rect
    matched_texts = []
    
    for block in text_dict.get("blocks", []):
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    
                    bbox = span.get("bbox")  # [tx0, ty0, tx1, ty1]
                    if not bbox:
                        continue
                        
                    # Calculate center of the text span
                    cx = (bbox[0] + bbox[2]) / 2.0
                    cy = (bbox[1] + bbox[3]) / 2.0
                    
                    # Check if center falls inside the shape rect (with a 2-point tolerance)
                    if (sx0 - 2 <= cx <= sx1 + 2) and (sy0 - 2 <= cy <= sy1 + 2):
                        # Keep track of text and coordinates for reading order sorting (top-down, left-right)
                        matched_texts.append((cy, cx, text))
                        
    matched_texts.sort()
    return " ".join(t[2] for t in matched_texts)

def point_to_rect_distance(px, py, rect):
    """Calculates the shortest distance between a point (px, py) and a rectangle rect [x0, y0, x1, y1]."""
    rx0, ry0, rx1, ry1 = rect
    dx = max(rx0 - px, 0, px - rx1)
    dy = max(ry0 - py, 0, py - ry1)
    return (dx**2 + dy**2)**0.5

def get_path_endpoints(d):
    """Retrieves the start and end coordinates of a drawing dictionary."""
    items = d.get("items", [])
    if not items:
        rect = d.get("rect")
        if rect:
            return [rect[0], rect[1]], [rect[2], rect[3]]
        return [0, 0], [0, 0]
        
    # If the drawing has a defined arrowhead, we can use it to determine end_pt exactly
    ah = d.get("arrowhead")
    if ah:
        bbox = ah["bbox"]
        end_pt = [(bbox[0]+bbox[2])/2.0, (bbox[1]+bbox[3])/2.0]
        
        # start_pt is the point on the first item furthest from end_pt
        first_item = items[0]
        if first_item["type"] == "line":
            p1 = first_item["p1"]
            p2 = first_item["p2"]
            d1 = ((p1[0]-end_pt[0])**2 + (p1[1]-end_pt[1])**2)**0.5
            d2 = ((p2[0]-end_pt[0])**2 + (p2[1]-end_pt[1])**2)**0.5
            start_pt = p1 if d1 > d2 else p2
        elif first_item["type"] == "rect":
            rx0, ry0, rx1, ry1 = first_item["bbox"]
            w = rx1 - rx0
            h = ry1 - ry0
            if w > h:
                cy = (ry0 + ry1) / 2.0
                start_pt = [rx0, cy] if abs(rx0 - end_pt[0]) > abs(rx1 - end_pt[0]) else [rx1, cy]
            else:
                cx = (rx0 + rx1) / 2.0
                start_pt = [cx, ry0] if abs(ry0 - end_pt[1]) > abs(ry1 - end_pt[1]) else [cx, ry1]
        else:
            rect = d.get("rect")
            start_pt = [rect[0], rect[1]]
            
        return start_pt, end_pt

    # Fallback for paths without arrowhead (like shafts) or general paths
    if len(items) == 1 and items[0]["type"] == "rect":
        bbox = items[0]["bbox"]
        rx0, ry0, rx1, ry1 = bbox
        w = rx1 - rx0
        h = ry1 - ry0
        if w > h:
            cy = (ry0 + ry1) / 2.0
            return [rx0, cy], [rx1, cy]
        else:
            cx = (rx0 + rx1) / 2.0
            return [cx, ry0], [cx, ry1]

    # Multiple items or non-rect items
    first_item = items[0]
    if first_item["type"] == "line":
        start_pt = first_item["p1"]
    elif first_item["type"] == "rect":
        rect = d.get("rect")
        est_end = [rect[2], rect[3]]
        rx0, ry0, rx1, ry1 = first_item["bbox"]
        w = rx1 - rx0
        h = ry1 - ry0
        if w > h:
            cy = (ry0 + ry1) / 2.0
            start_pt = [rx0, cy] if abs(rx0 - est_end[0]) > abs(rx1 - est_end[0]) else [rx1, cy]
        else:
            cx = (rx0 + rx1) / 2.0
            start_pt = [cx, ry0] if abs(ry0 - est_end[1]) > abs(ry1 - est_end[1]) else [cx, ry1]
    else:
        rect = d.get("rect")
        start_pt = [rect[0], rect[1]]
        
    last_item = items[-1]
    if last_item["type"] == "line":
        end_pt = last_item["p2"]
    elif last_item["type"] == "rect":
        rx0, ry0, rx1, ry1 = last_item["bbox"]
        w = rx1 - rx0
        h = ry1 - ry0
        if w > h:
            cy = (ry0 + ry1) / 2.0
            end_pt = [rx1, cy] if abs(rx1 - start_pt[0]) > abs(rx0 - start_pt[0]) else [rx0, cy]
        else:
            cx = (rx0 + rx1) / 2.0
            end_pt = [cx, ry1] if abs(ry1 - start_pt[1]) > abs(ry0 - start_pt[1]) else [cx, ry0]
    else:
        rect = d.get("rect")
        end_pt = [rect[2], rect[3]]
        
    return start_pt, end_pt

def try_merge_split_arrow(arrow, shafts, floating_labels, gap_threshold=25.0):
    """
    Checks if an arrow (with arrowhead) is the continuation of a split shaft segment
    separated by a floating label in the middle.
    Returns (merged_start, merged_end, label_text) if a match is found, else None.
    """
    arr_start, arr_end = get_path_endpoints(arrow)
    v_arr = [arr_end[0] - arr_start[0], arr_end[1] - arr_start[1]]
    
    for sh in shafts:
        pA, pB = get_path_endpoints(sh)
        # Orient shaft to align with the arrow's flow direction
        dot = (pB[0] - pA[0]) * v_arr[0] + (pB[1] - pA[1]) * v_arr[1]
        if dot >= 0:
            sh_start, sh_end = pA, pB
        else:
            sh_start, sh_end = pB, pA
            
        # 1. Distance Rule: Check if the gap is within 2x gap threshold
        gap_dist = ((sh_end[0] - arr_start[0])**2 + (sh_end[1] - arr_start[1])**2)**0.5
        if gap_dist > gap_threshold * 2.0:
            continue
            
        # 2. Direction Rule: Check if both segments point in the same direction
        v_sh = [sh_end[0] - sh_start[0], sh_end[1] - sh_start[1]]
        
        len_sh = (v_sh[0]**2 + v_sh[1]**2)**0.5
        len_arr = (v_arr[0]**2 + v_arr[1]**2)**0.5
        if len_sh < 1.0 or len_arr < 1.0:
            continue
            
        cos_theta = (v_sh[0] * v_arr[0] + v_sh[1] * v_arr[1]) / (len_sh * len_arr)
        if cos_theta < 0.92:  # Same direction check
            continue
            
        # 3. Collinearity Rule: Check alignment
        is_vertical = abs(v_arr[0]) < 3.0 and abs(v_sh[0]) < 3.0
        is_horizontal = abs(v_arr[1]) < 3.0 and abs(v_sh[1]) < 3.0
        
        if is_vertical:
            if abs(sh_end[0] - arr_start[0]) > 6.0:
                continue
        elif is_horizontal:
            if abs(sh_end[1] - arr_start[1]) > 6.0:
                continue
        else:
            # Perpendicular distance to the line defined by the arrow
            dx = arr_end[0] - arr_start[0]
            dy = arr_end[1] - arr_start[1]
            dist_to_line = abs(dy * sh_end[0] - dx * sh_end[1] + (dx * arr_start[1] - dy * arr_start[0])) / (dx**2 + dy**2)**0.5
            if dist_to_line > 6.0:
                continue
                
        # 4. Text Location Rule: Check if label center is between shaft end and arrow start
        for lbl in floating_labels:
            lx, ly = lbl["center"]
            dist_to_sh = ((lx - sh_end[0])**2 + (ly - sh_end[1])**2)**0.5
            dist_to_arr = ((lx - arr_start[0])**2 + (ly - arr_start[1])**2)**0.5
            
            if dist_to_sh < gap_threshold and dist_to_arr < gap_threshold:
                return sh_start, arr_end, lbl["text"]
                
    return None

def get_image_bboxes(page):
    """
    Extracts bounding boxes of all images on a page using:
    1. page.get_images() and page.get_image_rects()
    2. page.get_text("dict") image blocks (type == 1)
    """
    bboxes = []
    
    # 1. Use PyMuPDF get_image_rects()
    try:
        for img in page.get_images():
            name = img[7]
            for r in page.get_image_rects(name):
                bboxes.append((r.x0, r.y0, r.x1, r.y1))
    except Exception as e:
        pass
        
    # 2. Use page.get_text("dict") image blocks
    try:
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") == 1:
                bbox = block.get("bbox")
                bboxes.append(bbox)
    except Exception as e:
        pass
        
    # De-duplicate bounding boxes
    unique_bboxes = []
    for b in bboxes:
        exists = False
        for ub in unique_bboxes:
            if abs(ub[0] - b[0]) < 1.0 and abs(ub[1] - b[1]) < 1.0 and \
               abs(ub[2] - b[2]) < 1.0 and abs(ub[3] - b[3]) < 1.0:
                exists = True
                break
        if not exists:
            unique_bboxes.append(b)
            
    return unique_bboxes

def is_drawing_inside_image(drawing_rect, image_bboxes):
    """
    Checks if a drawing's bounding box is inside or significantly overlaps with
    any of the extracted image bounding boxes.
    """
    sx0, sy0, sx1, sy1 = drawing_rect
    for ix0, iy0, ix1, iy1 in image_bboxes:
        # Check if drawing_rect is fully enclosed by image_rect (with 2 points tolerance)
        if (sx0 >= ix0 - 2) and (sy0 >= iy0 - 2) and (sx1 <= ix1 + 2) and (sy1 <= iy1 + 2):
            return True
            
        # Or if the drawing overlaps heavily with the image (area intersection ratio > 80%)
        x_left = max(sx0, ix0)
        y_top = max(sy0, iy0)
        x_right = min(sx1, ix1)
        y_bottom = min(sy1, iy1)
        
        if x_right > x_left and y_bottom > y_top:
            inter_area = (x_right - x_left) * (y_bottom - y_top)
            shape_area = (sx1 - sx0) * (sy1 - sy0)
            if shape_area > 0 and (inter_area / shape_area) > 0.8:
                return True
                
    return False

def parse_pdf(pdf_path: str):
    """
    Parses both text (get_text('dict')) and shapes (get_drawings()) from the PDF.
    Saves text.json and shapes.json.
    Prints all extracted information clearly in the terminal.
    """
    if not os.path.exists(pdf_path):
        print(f"Error: Target PDF file '{pdf_path}' does not exist.")
        return None, None

    print(f"\n=======================================================")
    print(f"   STARTING PYMUPDF PDF PARSING: {os.path.basename(pdf_path)}")
    print(f"=======================================================\n")
    
    doc = fitz.open(pdf_path)
    
    all_pages_text = {}
    all_pages_shapes = {}
    
    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        print(f"--- Processing Page {page_num} ---")
        
        # 1. Extract Text
        raw_text_dict = page.get_text("dict")
        text_dict = make_serializable(raw_text_dict)
        all_pages_text[str(page_num)] = text_dict
        
        # 2. Extract image bounding boxes
        image_bboxes = get_image_bboxes(page)
        
        # 3. Extract Drawings (Shapes) and filter out shapes inside images & white background masks
        raw_drawings = page.get_drawings()
        filtered_drawings = []
        for d in raw_drawings:
            rect = d.get("rect")
            if rect:
                rect_tuple = (rect.x0, rect.y0, rect.x1, rect.y1)
                # Filter out shapes inside or heavily overlapping image blocks
                if is_drawing_inside_image(rect_tuple, image_bboxes):
                    continue
                    
            # Filter out white background mask rectangles (invisible text backgrounds)
            color = d.get("color")
            fill = d.get("fill")
            if is_white(color) and (fill is None or is_white(fill)):
                continue
            if color is None and is_white(fill):
                continue
                
            filtered_drawings.append(d)
            
        serialized_drawings = [serialize_drawing(d, text_dict) for d in filtered_drawings]
        
        # --- 4. Flowchart Relationship Detection (Nodes & Edges) ---
        # Identify nodes (Start/End bubbles, decision diamonds, process rectangles)
        nodes = []
        node_counter = 1
        for d in serialized_drawings:
            if d["classification"] in ["process_box", "decision_box", "start_end_terminal"]:
                d["id"] = f"node_{node_counter}"
                nodes.append(d)
                node_counter += 1
                
        # Find all arrows and shafts (potential split arrows)
        arrows = [d for d in serialized_drawings if d["classification"] == "arrow"]
        shafts = [d for d in serialized_drawings if d["classification"] == "arrow_shaft"]
        
        # Extract text labels not mapped to any box (like YES/NO branches)
        floating_labels = []
        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        txt = span.get("text", "").strip()
                        if not txt:
                            continue
                        # If this label is part of any node text, it is not a branch label
                        is_mapped = False
                        for node in nodes:
                            if txt in node["text"]:
                                is_mapped = True
                                break
                        if not is_mapped:
                            bbox = span.get("bbox")
                            if bbox:
                                cx = (bbox[0] + bbox[2]) / 2.0
                                cy = (bbox[1] + bbox[3]) / 2.0
                                floating_labels.append({"text": txt, "center": (cx, cy)})
                                
        # Calculate connections
        edges = []
        for arrow in arrows:
            items = arrow.get("items", [])
            if not items:
                continue
                
            # Check if this arrow is the second half of a split arrow merged with a shaft
            merged_info = try_merge_split_arrow(arrow, shafts, floating_labels)
            if merged_info:
                start_pt, end_pt, label_text = merged_info
            else:
                # Default start coordinate of the arrow
                first_item = items[0]
                if first_item["type"] == "line":
                    start_pt = first_item["p1"]
                elif first_item["type"] == "rect":
                    bbox = first_item["bbox"]
                    start_pt = [(bbox[0]+bbox[2])/2.0, (bbox[1]+bbox[3])/2.0]
                else:
                    rect = arrow["rect"]
                    start_pt = [(rect[0]+rect[2])/2.0, (rect[1]+rect[3])/2.0]
                    
                # Default end coordinate of the arrow (center of the arrowhead)
                ah = arrow.get("arrowhead")
                if ah:
                    bbox = ah["bbox"]
                    end_pt = [(bbox[0]+bbox[2])/2.0, (bbox[1]+bbox[3])/2.0]
                else:
                    last_item = items[-1]
                    if last_item["type"] == "line":
                        end_pt = last_item["p2"]
                    else:
                        rect = arrow["rect"]
                        end_pt = [(rect[0]+rect[2])/2.0, (rect[1]+rect[3])/2.0]
                        
                label_text = None
                    
            # Find closest source node (from)
            source_node = None
            min_src_dist = 999999.0
            for node in nodes:
                dist = point_to_rect_distance(start_pt[0], start_pt[1], node["rect"])
                if dist < min_src_dist:
                    min_src_dist = dist
                    source_node = node
                    
            # Find closest destination node (to)
            dest_node = None
            min_dst_dist = 999999.0
            for node in nodes:
                # Disallow connecting back to the exact same source node
                if source_node and node["id"] == source_node["id"]:
                    continue
                dist = point_to_rect_distance(end_pt[0], end_pt[1], node["rect"])
                if dist < min_dst_dist:
                    min_dst_dist = dist
                    dest_node = node
                    
            # Check if source and destination are within reasonable range
            if min_src_dist < 100.0 and min_dst_dist < 100.0 and source_node and dest_node:
                # If not already defined by split-merge, find nearby branch label text
                if label_text is None:
                    label_text = ""
                    best_lbl_dist = 40.0
                    for lbl in floating_labels:
                        lx, ly = lbl["center"]
                        lbl_dist = ((lx - start_pt[0])**2 + (ly - start_pt[1])**2)**0.5
                        if lbl_dist < best_lbl_dist:
                            best_lbl_dist = lbl_dist
                            label_text = lbl["text"]
                            
                edges.append({
                    "from": source_node["id"],
                    "from_text": source_node["text"],
                    "to": dest_node["id"],
                    "to_text": dest_node["text"],
                    "label": label_text
                })
                
        all_pages_shapes[str(page_num)] = {
            "nodes": [
                {
                    "id": n["id"],
                    "node_id": n["id"],
                    "type": n["classification"],
                    "text": n["text"],
                    "metadata": {
                        "page": int(page_num),
                        "bbox": n["rect"]
                    }
                } for n in nodes
            ],
            "edges": edges,
            "all_drawings": serialized_drawings
        }
        
        # 3. Print Summary of Text to Terminal
        print(f"  [Text Extraction]")
        text_blocks_count = len(text_dict.get("blocks", []))
        print(f"    - Total Text Blocks: {text_blocks_count}")
        
        # Read text content lines and print preview
        extracted_strings = []
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    if "spans" in line:
                        for span in line["spans"]:
                            txt = span.get("text", "").strip()
                            if txt:
                                extracted_strings.append(txt)
                                
        preview_text = " | ".join(extracted_strings[:10])
        print(f"    - Text Preview (First 10 items): {preview_text}")
        if len(extracted_strings) > 10:
            print(f"      ... and {len(extracted_strings) - 10} more text items.")
        
        # 4. Print Summary of Shapes to Terminal
        print(f"  [Shapes/Drawings Extraction]")
        print(f"    - Total Drawings Paths: {len(serialized_drawings)}")
        
        # Tally classified flowchart elements
        classification_counts = {
            "start_end_terminal": 0,
            "decision_box": 0,
            "process_box": 0,
            "arrow": 0,            # Path with shaft + arrowhead
            "arrow_shaft": 0,      # Path with shaft only
            "arrow_head": 0,       # Separate arrowhead path (if any)
            "other": 0,
            "noise": 0
        }
        for d in serialized_drawings:
            c = d.get("classification", "other")
            if c in classification_counts:
                classification_counts[c] += 1
            else:
                classification_counts["other"] += 1
                
        # Total shafts = count of 'arrow' (which has a shaft) + count of 'arrow_shaft' (shaft only)
        total_shafts = classification_counts["arrow"] + classification_counts["arrow_shaft"]
        # Total heads = count of 'arrow' (which has a head) + count of 'arrow_head' (head only)
        total_heads = classification_counts["arrow"] + classification_counts["arrow_head"]
        
        print(f"    - Flowchart Element Classification Counts:")
        print(f"      * Start/End Terminals:      {classification_counts['start_end_terminal']}")
        print(f"      * Decision Boxes (Diamonds): {classification_counts['decision_box']}")
        print(f"      * Process Boxes (Rectangles): {classification_counts['process_box']}")
        print(f"      * Arrow Connector Shafts:    {total_shafts}")
        print(f"      * Arrow Heads (Pointers):    {total_heads}")
        print(f"      * Other Geometries:          {classification_counts['other']}")
        if classification_counts['noise'] > 0:
            print(f"      * Noise (Filtered tiny paths): {classification_counts['noise']}")
            
        # Print detected connection edges
        if edges:
            print("    - Detected Flowchart Connection Edges:")
            for edge in edges:
                label_str = f" --[{edge['label']}]--> " if edge["label"] else " ----> "
                src_txt = (edge["from_text"][:28] + "...") if len(edge["from_text"]) > 28 else edge["from_text"]
                dst_txt = (edge["to_text"][:28] + "...") if len(edge["to_text"]) > 28 else edge["to_text"]
                print(f"      * {src_txt}{label_str}{dst_txt}")
        
        # Detail printing of the first few shapes for terminal output
        if serialized_drawings:
            print("    - Shape Details (First 5 paths):")
            for j, d in enumerate(serialized_drawings[:5]):
                fill_str = f"Fill: {d['fill']}" if d['fill'] else "No Fill"
                color_str = f"Color: {d['color']}" if d['color'] else "No Color"
                text_preview = f", Text: '{d['text']}'" if d.get("text") else ""
                print(f"      * Path {j+1}: Classification: '{d['classification']}'{text_preview}, Bbox: {d['rect']}, {color_str}, {fill_str}")
                for item_idx, item in enumerate(d["items"][:3]):
                    if item["type"] == "line":
                        print(f"        Line: {item['p1']} -> {item['p2']}")
                    elif item["type"] == "rect":
                        print(f"        Rect: BBox: {item['bbox']}")
                    elif item["type"] == "curve":
                        print(f"        Curve: P1: {item['p1']} ... P4: {item['p4']}")
                    elif item["type"] == "quad":
                        print(f"        Quad: {item['points']}")
                if len(d["items"]) > 3:
                    print(f"        ... and {len(d['items']) - 3} more drawing segments.")
            if len(serialized_drawings) > 5:
                print(f"      ... and {len(serialized_drawings) - 5} more drawing paths.")
        print("-" * 40 + "\n")
        
    doc.close()
    
    # Save output to JSON files
    text_json_path = "text.json"
    shapes_json_path = "shapes.json"
    decision_graph_json_path = "decision_graph.json"
    simplified_graph_json_path = "simplified_decision_graph.json"
    paragraphs_json_path = "paragraphs.json"
    
    # Construct clean decision graph
    decision_graph = {}
    for page_num, page_data in all_pages_shapes.items():
        decision_graph[page_num] = {
            "nodes": page_data["nodes"],
            "edges": page_data["edges"]
        }
    
    with open(text_json_path, "w", encoding="utf-8") as f:
        json.dump(all_pages_text, f, indent=2)
        
    with open(shapes_json_path, "w", encoding="utf-8") as f:
        json.dump(all_pages_shapes, f, indent=2)
        
    with open(decision_graph_json_path, "w", encoding="utf-8") as f:
        json.dump(decision_graph, f, indent=2)
        
    # Execute modular pipeline
    print("\n--- Running Modular RAG Pipeline ---")
    try:
        from services.graph_simplifier import simplify_graph_file
        from services.paragraph_generator import generate_paragraphs_file
        from services.semantic_chunker import chunk_paragraphs, SemanticChunker
        from services.vector_store import VectorStoreManager
        
        print(f"1. Simplifying graph from {decision_graph_json_path}...")
        simplified_graph = simplify_graph_file(decision_graph_json_path, simplified_graph_json_path)
        print(f"   Saved simplified graph to: {simplified_graph_json_path}")
        
        print(f"2. Generating troubleshooting paragraphs...")
        pdf_filename = os.path.basename(pdf_path)
        paragraphs = generate_paragraphs_file(simplified_graph_json_path, paragraphs_json_path, manual_name=pdf_filename)
        print(f"   Generated {len(paragraphs)} troubleshooting paragraphs. Saved to: {paragraphs_json_path}")
        
        print(f"3. Running semantic chunking...")
        chunker = SemanticChunker()
        chunks = chunk_paragraphs(paragraphs, chunker=chunker)
        print(f"   Created {len(chunks)} semantic chunks.")
        
        print(f"4. Generating embeddings and storing in ChromaDB...")
        vector_manager = VectorStoreManager()
        vector_manager.index_chunks(chunks)
        
    except Exception as e:
        import traceback
        print(f"Error executing modular pipeline: {e}")
        traceback.print_exc()
        
    print(f"=======================================================")
    print(f"   PARSING COMPLETED SUCCESSFULLY!")
    print(f"   - Saved text to: {os.path.abspath(text_json_path)}")
    print(f"   - Saved shapes to: {os.path.abspath(shapes_json_path)}")
    print(f"   - Saved raw graph to: {os.path.abspath(decision_graph_json_path)}")
    print(f"   - Saved simplified graph to: {os.path.abspath(simplified_graph_json_path)}")
    print(f"   - Saved paragraphs to: {os.path.abspath(paragraphs_json_path)}")
    print(f"=======================================================\n")
    
    return all_pages_text, all_pages_shapes

if __name__ == "__main__":
    # Test execution
    parse_pdf("data/sample.pdf")
