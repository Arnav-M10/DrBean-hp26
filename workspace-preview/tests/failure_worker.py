"""Frontend QA fault fixture only: real Worker/Counterdex; fail model after evidence.

Never used by product startup. No provider is constructed and no scientific
result is fabricated. Mirrors the retained post-science failure regression.
"""
from langchain_core.messages import ToolMessage
from bean_api.providers import ProviderFailure
from bean_api.research_controlled import ControlledResearchModel
import bean_api.research_controlled as controlled
from bean_api.worker import main


class FailAfterEvidence(ControlledResearchModel):
    def _generate(self, messages, **kwargs):
        if any(isinstance(message, ToolMessage) and message.name == "read_research_evidence" for message in messages):
            raise ProviderFailure("preferred_qa_post_science_failure")
        return super()._generate(messages, **kwargs)


controlled.build_controlled_research_model = FailAfterEvidence
if __name__ == "__main__":
    main()
