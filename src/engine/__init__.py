from .components import (Component, PageBreakComponent, Rect, ShapeComponent,
                         TextComponent, TextStyle, component_from_dict)
from .context import flatten_context, group_variables
from .parser import extract_fields, interpolate_template
from .template_engine import TemplateEngine
