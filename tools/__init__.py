import logging

logger = logging.getLogger(__name__)

try:
    from .basic_df_tools import df_tools
except ImportError:
    df_tools = []
    logger.warning("basic_df_tools unavailable")

try:
    from .basic_web_tools import web_tools
except ImportError:
    web_tools = []
    logger.warning("basic_web_tools unavailable")

try:
    from .basic_forensic_tools import forensic_tools
except ImportError:
    forensic_tools = []
    logger.warning("basic_forensic_tools unavailable")

try:
    from .google_maps_tools import google_maps_tools
except ImportError:
    google_maps_tools = []
    logger.warning("google_maps_tools unavailable")

try:
    from .milvus_tools import milvus_tools
except ImportError:
    milvus_tools = []
    logger.warning("milvus_tools unavailable")

basic_tools = {}
basic_tools["df_tools"] = df_tools + forensic_tools
basic_tools["web_tools"] = web_tools + google_maps_tools
basic_tools["milvus_tools"] = milvus_tools
