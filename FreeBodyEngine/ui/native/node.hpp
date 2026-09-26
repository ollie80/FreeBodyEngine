#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cmath>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

// Native tree node underlying FreeBodyEngine's UI system. Python's
// UIElement *is* this class (bound directly via pybind11 - see the
// //@bind marker below), not a wrapper around it: every add_child()/
// set_style()/calculate_layout() call from Python reaches this object
// with no extra Python-level indirection in front of it (option (a) from
// the C++-rewrite design discussion this came out of, over a wrapper
// class that would add one Python method dispatch per call for no
// benefit).
//
// Ported faithfully from ui/element.py (line references are to that file
// as it stood when this was written - see its own DEFAULT_STYLES/
// calculate_layout/get_current_styles/_update_scrollbar for the source
// of truth this was read from, not reinvented against): state-merged
// styles with the same memoization element.py's own get_current_styles()
// added (and documented as a *measured* fix, not a guess), fixed/
// percentage sizing, "auto" sizing via the same two-pass measure-then-
// layout scheme _measure_flow_extent implements, padding, gap, vertical/
// horizontal flow, anchor positioning, overflow/scroll clamping and
// scrollbar track/thumb geometry, and content_scale.
//
// DELIBERATELY NOT PORTED, by design rather than oversight:
//   - Style transition ANIMATIONS (element.py's UIAnimation) stay
//     Python-side permanently, not just "not yet ported" - they're a
//     cold path (only elements actively mid-transition touch it at all,
//     never the bulk per-frame layout/hit-test/style-merge work this
//     rewrite targets), and they interpolate arbitrary Python easing
//     curves plus string/tuple-shaped values (colors, "50w"-style size
//     strings) - porting that machinery into C++ would mean calling back
//     into Python every animated frame anyway, for a part of the system
//     that was never the performance problem. Python drives them the
//     same way it always did, just landing each frame's interpolated
//     value via this class's set_style() instead of the old UIElement's.
//   - Text measurement - never affected layout to begin with (see the
//     "Text" style docs in the old element.py: text is drawn *over* an
//     element's already-computed rect via UIRenderer's own MSDF
//     pipeline, sizing is always explicit). Nothing to port.
//   - Everything in ui/manager.py - mouse hover/click/focus/drag/scroll
//     dispatch and keyboard text-editing - is the next slice, still
//     Python-side, operating against this class the same way it operated
//     against UIElement (hit_test()/emit()/set_state()/
//     get_current_styles() already match those call patterns).
//@bind
class Node : public std::enable_shared_from_this<Node> {
public:
    explicit Node(pybind11::dict default_styles);

    void add_child(std::shared_ptr<Node> child);
    void remove_child(std::shared_ptr<Node> child);
    std::vector<std::shared_ptr<Node>> get_children();

    void set_style(std::string name, pybind11::object value);
    pybind11::object get_style(std::string name);
    pybind11::dict get_current_styles();

    void set_state(std::string state);
    std::string get_state();

    void on(std::string event, pybind11::function callback);
    void off(std::string event, pybind11::function callback);
    void clear_event(std::string event);
    void emit(std::string event, pybind11::args args);
    bool has_event(std::string event);

    void calculate_layout(double parent_x, double parent_y, double parent_w, double parent_h, double root_w, double root_h, double scale);
    void calculate_root_layout(double width, double height, double scale);

    std::shared_ptr<Node> hit_test(double px, double py);

    // get_overflow() takes a required `current_styles` argument (the
    // caller's own already-fetched get_current_styles() result, to avoid
    // recomputing it) rather than the old Python get_overflow(styles=None)
    // method's optional one - pybind11 doesn't pick up a C++ default
    // argument as an optional one on the Python side without an explicit
    // py::arg(...) annotation the //@bind pipeline doesn't support yet, so
    // the Python-side UIElement wrapper (ui/native_element.py) is the one
    // that supplies "compute it from get_current_styles() if not given",
    // then calls this.
    std::string get_overflow(pybind11::dict current_styles);

    // Safe (shared_ptr, not raw-pointer) accessors for the two relationships
    // that would otherwise need to expose a raw Node* to Python - see
    // add_child()'s own docstring on why parent_/scrollbar_owner_ are raw,
    // non-owning pointers internally. Returning shared_ptr here is what
    // enable_shared_from_this is for: it hands Python a properly refcounted
    // reference to the *same* underlying object other shared_ptrs already
    // own, not a second, independently-owned copy - the double-free risk a
    // plain `Node*` return (or a `def_readwrite` on one) would carry.
    std::shared_ptr<Node> get_parent();
    std::shared_ptr<Node> scrollbar_owner();

    double x = 0.0;
    double y = 0.0;
    double width = 0.0;
    double height = 0.0;
    pybind11::dict styles;

    double _scroll_offset = 0.0;
    double _scroll_max = 0.0;
    double _scroll_viewport_extent = 0.0;
    double _scroll_content_extent = 0.0;
    std::string _scroll_dir = "vertical";

    // Plain public bools, not the leading-underscore-but-still-private
    // convention the rest of this class otherwise uses - named to match
    // element.py's own `_is_scrollbar_part`/etc *exactly* (including the
    // leading underscore) since ui/manager.py reads them as plain
    // attributes (`getattr(hit, "_is_scrollbar_thumb", False)`) on
    // whichever backend is active, and matching the name outright avoids
    // needing a Python-side property shim for these three specifically.
    bool _is_scrollbar_part = false;
    bool _is_scrollbar_track = false;
    bool _is_scrollbar_thumb = false;

private:
    std::vector<std::shared_ptr<Node>> children_;
    Node* parent_ = nullptr;
    pybind11::dict default_styles_;
    pybind11::object styles_cache_ = pybind11::none();
    std::string state_ = "normal";
    std::unordered_map<std::string, std::vector<pybind11::function>> event_callbacks_;

    Node* scrollbar_owner_ = nullptr;
    std::shared_ptr<Node> scrollbar_track_;
    std::shared_ptr<Node> scrollbar_thumb_;

    bool has_own_style(const std::string& key);
    double measure_flow_extent(double content_w, double content_h, double root_w, double root_h, double scale, const std::string& layout_dir, double gap);
    void apply_anchor(const std::string& parent_anchor, const std::string& anchor, double container_x, double container_y, double container_w, double container_h, double offset_x, double offset_y);
    void layout_flow_children(double content_x, double content_y, double content_w, double content_h, double root_w, double root_h, double scale, const std::string& layout_dir, double gap);
    void update_scrollbar(pybind11::dict& current_styles, const std::string& overflow, const std::string& layout_dir, double content_x, double content_y, double content_w, double content_h, double scale);
};

// -- helpers --------------------------------------------------------------
// `inline` throughout (this header is include-only, see BoundFile's own
// docstring in cli/cpp/compile.py) - it may end up #include-d into more
// than one generated bind shim once a second native file references
// Node, and a non-inline definition in a header would then duplicate-
// define these across translation units at link time.

namespace {

// Mirrors element.py's _parse_size for the subset this covers - a plain
// number (raw pixels, scaled by `scale` the same way _parse_size scales
// by window.content_scale) or a "<number><suffix>" string where suffix
// is "w"/"h" (percent of the immediate parent's width/height) or "ww"/
// "hw" (percent of the root/window's width/height). Anything else
// (including "auto", which calculate_layout() below special-cases before
// ever calling this, same as the Python original) returns 0, consistent
// with element.py's own "a bad style shouldn't crash the whole layout
// pass" philosophy - no logger binding exists on this side yet to warn
// through, so this fails silently rather than not at all.
inline double parse_size(const pybind11::object& value, double parent_w, double parent_h, double root_w, double root_h, double scale) {
    if (pybind11::isinstance<pybind11::int_>(value) || pybind11::isinstance<pybind11::float_>(value)) {
        return value.cast<double>() * scale;
    }

    std::string s = pybind11::str(value).cast<std::string>();
    if (s.empty()) {
        return 0.0;
    }

    try {
        size_t consumed = 0;
        double as_number = std::stod(s, &consumed);
        if (consumed == s.size()) {
            return as_number * scale;
        }
    } catch (...) {
        // Falls through to the suffix parse below.
    }

    auto ends_with = [&](const std::string& suffix) {
        return s.size() >= suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
    };

    try {
        if (ends_with("ww")) {
            return std::stod(s.substr(0, s.size() - 2)) / 100.0 * root_w;
        }
        if (ends_with("hw")) {
            return std::stod(s.substr(0, s.size() - 2)) / 100.0 * root_h;
        }
        if (ends_with("w")) {
            return std::stod(s.substr(0, s.size() - 1)) / 100.0 * parent_w;
        }
        if (ends_with("h")) {
            return std::stod(s.substr(0, s.size() - 1)) / 100.0 * parent_h;
        }
    } catch (...) {
        return 0.0;
    }

    return 0.0;
}

inline std::string style_str(pybind11::dict& styles, const char* key, const std::string& fallback) {
    pybind11::str k(key);
    if (styles.contains(k)) {
        return pybind11::str(styles[k]).cast<std::string>();
    }
    return fallback;
}

inline double style_size(pybind11::dict& styles, const char* key, double fallback_px, double parent_w, double parent_h, double root_w, double root_h, double scale) {
    pybind11::str k(key);
    if (styles.contains(k)) {
        return parse_size(styles[k], parent_w, parent_h, root_w, root_h, scale);
    }
    return fallback_px * scale;
}

inline std::shared_ptr<Node> hit_test_search(const std::vector<std::shared_ptr<Node>>& siblings, double px, double py) {
    // Topmost-first (later-added == drawn last == on top, matching
    // UIRenderer's own draw order) and deepest-match-wins - a direct
    // port of UIManager._hit_test's own two rules.
    for (auto it = siblings.rbegin(); it != siblings.rend(); ++it) {
        const auto& node = *it;
        if (node->width > 0 && node->height > 0 &&
            px >= node->x && px < node->x + node->width &&
            py >= node->y && py < node->y + node->height) {
            auto deeper = hit_test_search(node->get_children(), px, py);
            return deeper ? deeper : node;
        }
    }
    return nullptr;
}

} // namespace

inline Node::Node(pybind11::dict default_styles) : default_styles_(std::move(default_styles)) {}

inline void Node::add_child(std::shared_ptr<Node> child) {
    child->parent_ = this;
    children_.push_back(std::move(child));
}

inline void Node::remove_child(std::shared_ptr<Node> child) {
    for (auto it = children_.begin(); it != children_.end(); ++it) {
        if (*it == child) {
            (*it)->parent_ = nullptr;
            children_.erase(it);
            return;
        }
    }
}

inline std::vector<std::shared_ptr<Node>> Node::get_children() {
    // Returns a copy of the child list (shared_ptr copies are cheap,
    // refcount bumps) rather than exposing children_ by reference -
    // mutating the returned list from Python must never bypass
    // add_child()'s parent-wiring, the way a raw &children_ readwrite
    // property would let it.
    return children_;
}

inline void Node::set_style(std::string name, pybind11::object value) {
    styles[pybind11::str(name)] = value;
    styles_cache_ = pybind11::none();
}

inline pybind11::object Node::get_style(std::string name) {
    pybind11::str key(name);
    if (styles.contains(key)) {
        return styles[key];
    }
    return pybind11::none();
}

inline pybind11::dict Node::get_current_styles() {
    // Memoized - see element.py's own get_current_styles() docstring for
    // why (a *measured* fix for a real slowdown on list-heavy views, not
    // a guess): this gets called several times per element per frame
    // (calculate_layout, measure_flow_extent for an auto-sized parent,
    // plus whatever the still-Python UIManager/UIRenderer call it for),
    // so rebuilding the merged dict from scratch every time is real,
    // avoidable work. Invalidated by the only two things that can change
    // its result - set_style() and set_state() - same as the original.
    if (!styles_cache_.is_none()) {
        return styles_cache_.cast<pybind11::dict>();
    }

    pybind11::dict current;
    for (auto item : default_styles_) {
        current[item.first] = item.second;
    }
    for (auto item : styles) {
        current[item.first] = item.second;
    }

    pybind11::str state_key(state_);
    if (styles.contains(state_key)) {
        pybind11::object override_obj = styles[state_key];
        if (pybind11::isinstance<pybind11::dict>(override_obj)) {
            for (auto item : override_obj.cast<pybind11::dict>()) {
                current[item.first] = item.second;
            }
        }
    }

    styles_cache_ = current;
    return current;
}

inline void Node::set_state(std::string state) {
    if (state == state_) {
        return;
    }
    state_ = std::move(state);
    styles_cache_ = pybind11::none();
}

inline std::string Node::get_state() {
    return state_;
}

inline void Node::on(std::string event, pybind11::function callback) {
    event_callbacks_[event].push_back(std::move(callback));
}

inline void Node::off(std::string event, pybind11::function callback) {
    auto it = event_callbacks_.find(event);
    if (it == event_callbacks_.end()) {
        return;
    }
    auto& list = it->second;
    for (auto cb_it = list.begin(); cb_it != list.end(); ++cb_it) {
        // pybind11::function equality compares the underlying PyObject*
        // identity (via object::equal, itself PyObject_RichCompare) -
        // the same "is this literally the same callback" semantics
        // Python's own `callback in list` used in element.py's off().
        if (cb_it->equal(callback)) {
            list.erase(cb_it);
            return;
        }
    }
}

inline void Node::clear_event(std::string event) {
    event_callbacks_.erase(event);
}

inline void Node::emit(std::string event, pybind11::args args) {
    auto it = event_callbacks_.find(event);
    if (it == event_callbacks_.end()) {
        return;
    }
    // Copies the callback list first, same reason element.py's _emit
    // does - a callback that itself calls on()/off() on this same event
    // must not mutate the list out from under this loop.
    std::vector<pybind11::function> callbacks = it->second;
    for (auto& callback : callbacks) {
        callback(*args);
    }
}

inline bool Node::has_event(std::string event) {
    auto it = event_callbacks_.find(event);
    return it != event_callbacks_.end() && !it->second.empty();
}

inline bool Node::has_own_style(const std::string& key) {
    pybind11::str k(key);
    if (styles.contains(k)) {
        return true;
    }
    pybind11::str state_key(state_);
    if (styles.contains(state_key)) {
        pybind11::object override_obj = styles[state_key];
        if (pybind11::isinstance<pybind11::dict>(override_obj) && override_obj.cast<pybind11::dict>().contains(k)) {
            return true;
        }
    }
    return false;
}

inline std::string Node::get_overflow(pybind11::dict current_styles) {
    static const std::vector<std::string> valid = {"visible", "hidden", "scroll", "auto"};

    if (has_own_style("overflow")) {
        std::string value = style_str(current_styles, "overflow", "visible");
        if (std::find(valid.begin(), valid.end(), value) == valid.end()) {
            return "visible";
        }
        return value;
    }

    pybind11::str scroll_key("scroll");
    if (current_styles.contains(scroll_key) && current_styles[scroll_key].cast<bool>()) {
        return "auto";
    }

    return "visible";
}

inline double Node::measure_flow_extent(double content_w, double content_h, double root_w, double root_h, double scale, const std::string& layout_dir, double gap) {
    double total_extent = 0.0;
    bool seen_first = false;

    for (auto& child : children_) {
        if (child->_is_scrollbar_part) {
            continue;
        }
        bool child_anchored = child->has_own_style("anchor") || child->has_own_style("parent_anchor");
        if (child_anchored) {
            continue;
        }

        pybind11::dict child_styles = child->get_current_styles();
        const char* size_key = layout_dir == "vertical" ? "height" : "width";
        pybind11::str key(size_key);
        pybind11::object size_style = child_styles.contains(key) ? child_styles[key] : pybind11::cast(std::string("0"));

        double extent;
        std::string size_str = pybind11::isinstance<pybind11::str>(size_style) ? size_style.cast<std::string>() : std::string();
        if (size_str == "auto") {
            // Falls back to the child's own size from the *last* full
            // layout pass, same reasoning as element.py's own comment on
            // this exact line: this measurement runs before this
            // element's children are laid out for the current frame, so
            // "last frame's value" is one frame stale at worst and
            // self-corrects every frame after.
            extent = layout_dir == "vertical" ? child->height : child->width;
        } else {
            extent = parse_size(size_style, content_w, content_h, root_w, root_h, scale);
        }

        if (seen_first) {
            total_extent += gap;
        }
        total_extent += extent;
        seen_first = true;
    }

    return total_extent;
}

inline void Node::apply_anchor(const std::string& parent_anchor, const std::string& anchor, double container_x, double container_y, double container_w, double container_h, double offset_x, double offset_y) {
    static const std::unordered_map<std::string, std::pair<int, int>> positions = {
        {"top_left", {-1, 1}}, {"top_center", {0, 1}}, {"top_right", {1, 1}},
        {"center_left", {-1, 0}}, {"center", {0, 0}}, {"center_right", {1, 0}},
        {"bottom_left", {-1, -1}}, {"bottom_center", {0, -1}}, {"bottom_right", {1, -1}},
    };

    auto pit = positions.find(parent_anchor);
    auto ait = positions.find(anchor);
    if (pit == positions.end() || ait == positions.end()) {
        // Unknown anchor name - element.py warns and leaves position
        // untouched; no logger binding exists here yet, so this just
        // silently leaves x/y at whatever the caller already set (the
        // plain flow position), the same "don't crash the layout pass"
        // fallback used throughout.
        return;
    }

    int parent_x = pit->second.first, parent_y = pit->second.second;
    int anchor_x = ait->second.first, anchor_y = ait->second.second;

    double origin_x = container_x + ((parent_x + 1) / 2.0) * container_w;
    double origin_y = container_y + ((1 - parent_y) / 2.0) * container_h;

    x = origin_x - ((anchor_x + 1) / 2.0) * width + offset_x;
    y = origin_y - ((1 - anchor_y) / 2.0) * height + offset_y;
}

inline void Node::layout_flow_children(double content_x, double content_y, double content_w, double content_h, double root_w, double root_h, double scale, const std::string& layout_dir, double gap) {
    double child_offset_x = content_x;
    double child_offset_y = content_y;

    for (auto& child : children_) {
        if (child->_is_scrollbar_part) {
            continue;
        }

        bool child_anchored = child->has_own_style("anchor") || child->has_own_style("parent_anchor");
        if (child_anchored) {
            child->calculate_layout(content_x, content_y, content_w, content_h, root_w, root_h, scale);
            continue;
        }

        child->calculate_layout(child_offset_x, child_offset_y, content_w, content_h, root_w, root_h, scale);

        if (layout_dir == "vertical") {
            child_offset_y += child->height + gap;
        } else if (layout_dir == "horizontal") {
            child_offset_x += child->width + gap;
        }
    }
}

inline void Node::calculate_layout(double parent_x, double parent_y, double parent_w, double parent_h, double root_w, double root_h, double scale) {
    pybind11::dict current = get_current_styles();

    std::string layout_dir = style_str(current, "layout", "vertical");

    pybind11::str width_key("width"), height_key("height");
    pybind11::object width_style = current.contains(width_key) ? current[width_key] : pybind11::cast(std::string("0"));
    pybind11::object height_style = current.contains(height_key) ? current[height_key] : pybind11::cast(std::string("0"));

    bool auto_width = pybind11::isinstance<pybind11::str>(width_style) && width_style.cast<std::string>() == "auto";
    bool auto_height = pybind11::isinstance<pybind11::str>(height_style) && height_style.cast<std::string>() == "auto";

    width = auto_width ? 0.0 : parse_size(width_style, parent_w, parent_h, root_w, root_h, scale);
    height = auto_height ? 0.0 : parse_size(height_style, parent_w, parent_h, root_w, root_h, scale);

    double pad = style_size(current, "padding", 0.0, parent_w, parent_h, root_w, root_h, scale);
    double pad_left = style_size(current, "padding_left", pad / scale, parent_w, parent_h, root_w, root_h, scale);
    double pad_right = style_size(current, "padding_right", pad / scale, parent_w, parent_h, root_w, root_h, scale);
    double pad_top = style_size(current, "padding_top", pad / scale, parent_w, parent_h, root_w, root_h, scale);
    double pad_bottom = style_size(current, "padding_bottom", pad / scale, parent_w, parent_h, root_w, root_h, scale);

    double content_w = std::max(0.0, width - pad_left - pad_right);
    double content_h = std::max(0.0, height - pad_top - pad_bottom);
    double gap = style_size(current, "gap", 0.0, content_w, content_h, root_w, root_h, scale);

    if (auto_width || auto_height) {
        double measured = measure_flow_extent(content_w, content_h, root_w, root_h, scale, layout_dir, gap);
        if (auto_height && layout_dir == "vertical") {
            height = measured + pad_top + pad_bottom;
            content_h = std::max(0.0, height - pad_top - pad_bottom);
        } else if (auto_width && layout_dir == "horizontal") {
            width = measured + pad_left + pad_right;
            content_w = std::max(0.0, width - pad_left - pad_right);
        }
    }

    x = parent_x;
    y = parent_y;

    bool anchored = has_own_style("anchor") || has_own_style("parent_anchor");

    // Raw pixel offsets, deliberately not run through parse_size/
    // style_size (which would treat "x"/"y" as parseable sizes,
    // percentages included) - element.py only ever treats "x"/"y" as a
    // plain number of pixels multiplied by content_scale directly.
    pybind11::str x_key("x"), y_key("y");
    double raw_x = current.contains(x_key) && !pybind11::isinstance<pybind11::str>(current[x_key]) ? current[x_key].cast<double>() : 0.0;
    double raw_y = current.contains(y_key) && !pybind11::isinstance<pybind11::str>(current[y_key]) ? current[y_key].cast<double>() : 0.0;
    double x_offset = raw_x * scale;
    double y_offset = raw_y * scale;

    if (anchored) {
        std::string parent_anchor = style_str(current, "parent_anchor", "center");
        std::string anchor = style_str(current, "anchor", "bottom_left");
        apply_anchor(parent_anchor, anchor, parent_x, parent_y, parent_w, parent_h, x_offset, y_offset);
    } else {
        x += x_offset;
        y += y_offset;
    }

    double content_x = x + pad_left;
    double content_y = y + pad_top;

    std::string overflow = get_overflow(current);
    _scroll_dir = layout_dir;

    if (overflow == "scroll" || overflow == "auto") {
        double measured_extent = measure_flow_extent(content_w, content_h, root_w, root_h, scale, layout_dir, gap);
        double viewport_extent = layout_dir == "vertical" ? content_h : content_w;
        double max_scroll = std::max(0.0, measured_extent - viewport_extent);
        _scroll_offset = std::max(0.0, std::min(_scroll_offset, max_scroll));
        _scroll_max = max_scroll;
        _scroll_viewport_extent = viewport_extent;
        _scroll_content_extent = measured_extent;

        if (layout_dir == "vertical") {
            content_y -= _scroll_offset;
        } else {
            content_x -= _scroll_offset;
        }
    } else {
        _scroll_offset = 0.0;
        _scroll_max = 0.0;
        _scroll_viewport_extent = layout_dir == "vertical" ? content_h : content_w;
        _scroll_content_extent = _scroll_viewport_extent;
    }

    layout_flow_children(content_x, content_y, content_w, content_h, root_w, root_h, scale, layout_dir, gap);

    if (overflow == "scroll" || overflow == "auto") {
        update_scrollbar(current, overflow, layout_dir, content_x, content_y, content_w, content_h, scale);
    } else if (scrollbar_track_) {
        // No longer scrollable (overflow changed under it, or content
        // stopped overflowing) - zero out rather than destroy, so
        // nothing draws or hit-tests here without rebuilding the
        // elements if it becomes scrollable again later.
        scrollbar_track_->x = scrollbar_track_->y = scrollbar_track_->width = scrollbar_track_->height = 0.0;
        scrollbar_thumb_->x = scrollbar_thumb_->y = scrollbar_thumb_->width = scrollbar_thumb_->height = 0.0;
    }
}

inline void Node::calculate_root_layout(double win_width, double win_height, double scale) {
    // The root panel's own size is always exactly the window size, never
    // read from styles - see the old RootElement.calculate_layout, which
    // never calls _parse_size for its own width/height either.
    x = 0.0;
    y = 0.0;
    width = win_width;
    height = win_height;

    pybind11::dict current = get_current_styles();
    std::string layout_dir = style_str(current, "layout", "vertical");

    double pad = style_size(current, "padding", 0.0, win_width, win_height, win_width, win_height, scale);
    double pad_left = style_size(current, "padding_left", pad / scale, win_width, win_height, win_width, win_height, scale);
    double pad_right = style_size(current, "padding_right", pad / scale, win_width, win_height, win_width, win_height, scale);
    double pad_top = style_size(current, "padding_top", pad / scale, win_width, win_height, win_width, win_height, scale);
    double pad_bottom = style_size(current, "padding_bottom", pad / scale, win_width, win_height, win_width, win_height, scale);
    double gap = style_size(current, "gap", 0.0, win_width, win_height, win_width, win_height, scale);

    double content_x = pad_left;
    double content_y = pad_top;
    double content_w = std::max(0.0, win_width - pad_left - pad_right);
    double content_h = std::max(0.0, win_height - pad_top - pad_bottom);

    layout_flow_children(content_x, content_y, content_w, content_h, win_width, win_height, scale, layout_dir, gap);
}

inline std::shared_ptr<Node> Node::hit_test(double px, double py) {
    return hit_test_search(children_, px, py);
}

inline std::shared_ptr<Node> Node::get_parent() {
    return parent_ ? parent_->shared_from_this() : nullptr;
}

inline std::shared_ptr<Node> Node::scrollbar_owner() {
    return scrollbar_owner_ ? scrollbar_owner_->shared_from_this() : nullptr;
}

inline void Node::update_scrollbar(pybind11::dict& current_styles, const std::string& overflow, const std::string& layout_dir, double content_x, double content_y, double content_w, double content_h, double scale) {
    // Deliberately two real Node children rather than a special-cased
    // draw call, same reasoning as element.py's own _update_scrollbar:
    // adding them to children_ means the (still-Python, for now)
    // UIManager/UIRenderer already reach them for free via hit_test()/
    // get_children(), with zero changes needed in either.
    //
    // These come back to Python as plain Node, never UIElement, even
    // though the surrounding tree may be UIElement throughout - a
    // pybind11 object's Python type is fixed by where it's constructed,
    // and there's no reliable way to make a C++-constructed object come
    // back as an arbitrary Python subclass afterward (confirmed: a
    // set_node_factory()-style "construct via a stored Python callable,
    // extract via .cast<shared_ptr<Node>>()" approach was tried and
    // still lost the subclass on the way back - pybind11's shared_ptr
    // round-trip doesn't preserve it for a plain, trampoline-less Python
    // subclass, and reassigning __class__ on the returned bare Node is
    // also refused by CPython, since UIElement's __dict__ gives it a
    // different deallocator). ui/native_element.py's UIElement.children
    // property is what actually papers over this - it wraps any bare
    // Node it gets back from get_children() in a small cached proxy
    // (_ScrollbarPartProxy) supplying just the UIElement-only surface
    // (.children/._layout/.state/etc) that ui/manager.py and
    // ui/renderer.py need, delegating everything else straight through -
    // a real (if rare - at most 2 elements per scrollable container)
    // exception to "every element is UIElement itself, zero wrapper",
    // not a fix here.
    bool first_time = !scrollbar_track_;
    if (first_time) {
        scrollbar_track_ = std::make_shared<Node>(default_styles_);
        scrollbar_thumb_ = std::make_shared<Node>(default_styles_);
        scrollbar_track_->_is_scrollbar_part = true;
        scrollbar_thumb_->_is_scrollbar_part = true;
        scrollbar_track_->_is_scrollbar_track = true;
        scrollbar_thumb_->_is_scrollbar_thumb = true;
        scrollbar_thumb_->scrollbar_owner_ = this;
        add_child(scrollbar_track_);
        scrollbar_track_->add_child(scrollbar_thumb_);
        // The click-to-jump-to-position behavior on the track itself
        // (element.py's on_track_click) needs live mouse position, which
        // only the still-Python UIManager currently polls each frame -
        // left for that slice to wire up via track.on("click", ...) from
        // the Python side, the same on()/emit() path every other click
        // handler in this system already uses.
    }

    // "auto" only actually shows the bar once there's real overflow to
    // scroll to - "scroll" always shows it, per the OVERFLOW docs.
    if (overflow == "auto" && _scroll_max <= 0.0) {
        scrollbar_track_->x = scrollbar_track_->y = scrollbar_track_->width = scrollbar_track_->height = 0.0;
        scrollbar_thumb_->x = scrollbar_thumb_->y = scrollbar_thumb_->width = scrollbar_thumb_->height = 0.0;
        return;
    }

    pybind11::str track_key("scrollbar_track"), thumb_key("scrollbar_thumb");
    if (current_styles.contains(track_key) && pybind11::isinstance<pybind11::dict>(current_styles[track_key])) {
        for (auto item : current_styles[track_key].cast<pybind11::dict>()) {
            scrollbar_track_->styles[item.first] = item.second;
        }
    }
    if (current_styles.contains(thumb_key) && pybind11::isinstance<pybind11::dict>(current_styles[thumb_key])) {
        for (auto item : current_styles[thumb_key].cast<pybind11::dict>()) {
            scrollbar_thumb_->styles[item.first] = item.second;
        }
    }
    scrollbar_track_->styles_cache_ = pybind11::none();
    scrollbar_thumb_->styles_cache_ = pybind11::none();

    double sb_width = style_size(current_styles, "scrollbar_width", 8.0, content_w, content_h, content_w, content_h, scale);
    double margin = style_size(current_styles, "scrollbar_margin", 2.0, content_w, content_h, content_w, content_h, scale);
    double min_thumb = style_size(current_styles, "scrollbar_min_thumb", 24.0, content_w, content_h, content_w, content_h, scale);

    double viewport = _scroll_viewport_extent;
    double content_extent = _scroll_content_extent;
    double ratio = content_extent > 0.0 ? viewport / content_extent : 1.0;
    double fraction = _scroll_max > 0.0 ? _scroll_offset / _scroll_max : 0.0;

    double track_x, track_y, track_w, track_h;
    if (layout_dir == "vertical") {
        track_x = content_x + content_w - sb_width - margin;
        track_y = content_y;
        track_w = sb_width;
        track_h = content_h;

        double thumb_h = std::max(min_thumb, std::min(track_h, track_h * ratio));
        double travel = std::max(0.0, track_h - thumb_h);
        scrollbar_thumb_->x = track_x;
        scrollbar_thumb_->y = track_y + fraction * travel;
        scrollbar_thumb_->width = sb_width;
        scrollbar_thumb_->height = thumb_h;
    } else {
        track_x = content_x;
        track_y = content_y + content_h - sb_width - margin;
        track_w = content_w;
        track_h = sb_width;

        double thumb_w = std::max(min_thumb, std::min(track_w, track_w * ratio));
        double travel = std::max(0.0, track_w - thumb_w);
        scrollbar_thumb_->x = track_x + fraction * travel;
        scrollbar_thumb_->y = track_y;
        scrollbar_thumb_->width = thumb_w;
        scrollbar_thumb_->height = sb_width;
    }

    scrollbar_track_->x = track_x;
    scrollbar_track_->y = track_y;
    scrollbar_track_->width = track_w;
    scrollbar_track_->height = track_h;
}
