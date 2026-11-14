"""General research files, source citations and Gemini analysis (contract ``general-research.v1``).

Integration (owned by the application assembler):

    from bean_api.general_research import register_general_routes, general_research_capabilities
    app = create_app(settings)
    register_general_routes(app)                       # live/disabled from the server's ProviderConfig
    ... "general_research": general_research_capabilities(app) in /capabilities

Uploads never send anything to a provider. An analysis sends exactly the consented
files and question in one accounted request, and its result is always labelled
``not_mathematically_verified``.
"""
from .routes import default_transport, general_research_capabilities, register_general_routes  # noqa: F401
