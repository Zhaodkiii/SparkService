_DEFAULT_CHAT = {
    "endpoint": "",
    "model": "",
    "temperature": 0.2,
    "max_tokens": 4096,
}
_DEFAULT_EMBED = {
    "endpoint": "",
    "model": "",
    "temperature": 0.0,
    "max_tokens": 2048,
}

DEFAULT_SCENARIOS = {
    "chat": dict(_DEFAULT_CHAT),
    "embedding": dict(_DEFAULT_EMBED),
    "voice": dict(_DEFAULT_CHAT),
    "medical_structured_extraction": {},
    "medical_document_type_recognition": {},
    "medical_case_extraction": {},
    "health_exam_extraction": {},
    "medical_report_extraction": {},
    "prescription_extraction": {},
    "medication_extraction": {},
    "medicine_box_extraction": {},
    "optimization_text": {
        "endpoint": "",
        "model": "",
        "temperature": 0.0,
        "max_tokens": 4096,
    },
    "optimization_visual": dict(_DEFAULT_CHAT),
    "context_folding": dict(_DEFAULT_CHAT),
    "router": dict(_DEFAULT_CHAT),
    "model_config": dict(_DEFAULT_EMBED),
    "report_interpretation": dict(_DEFAULT_CHAT),
    "nutrition_intake_extraction": dict(_DEFAULT_CHAT),
}

DEFAULT_API_KEYS = []

DEFAULT_SEARCH_KEYS = [
    {
        "name": "Spark Search",
        "company": "SPARK",
        "key": "",
        "request_url": "https://api.sparkclient.local/v1/search",
        "is_using": True,
        "search_class": "web",
        "help": "Default web search connector",
        "source": "system",
    },
    {
        "name": "Tavily Search",
        "company": "TAVILY",
        "key": "",
        "request_url": "https://api.tavily.com/search",
        "is_using": False,
        "search_class": "web",
        "help": "RAG retrieval provider",
        "source": "system",
    },
]

DEFAULT_TOOL_KEYS = [
    {
        "name": "Spark Tools",
        "company": "SPARK",
        "key": "",
        "request_url": "https://api.sparkclient.local/v1/tools",
        "is_using": True,
        "tool_class": "native",
        "help": "Spark default tools",
        "source": "system",
    },
    {
        "name": "Mapbox",
        "company": "MAPBOX",
        "key": "",
        "request_url": "https://api.mapbox.com",
        "is_using": False,
        "tool_class": "map",
        "help": "Map geocoding / route tool",
        "source": "system",
    },
]

DEFAULT_MODELS = []

DEFAULT_USER_INFO = {
    "choose_embedding_model": "",
    "optimization_text_model": "",
    "optimization_visual_model": "",
    "text_to_speech_model": "",
    "use_knowledge": True,
    "knowledge_count": 5,
    "knowledge_similarity": 0.75,
    "use_search": True,
    "bilingual_search": False,
    "search_count": 3,
    "use_map": False,
    "use_calendar": False,
    "use_weather": False,
    "use_canvas": False,
    "use_code": False,
}
