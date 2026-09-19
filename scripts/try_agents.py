"""Try the agents with the real Gemini model (uses your API key).

Run from the project root:
    python -m scripts.try_agents
    python -m scripts.try_agents --request "I want a quick vegan breakfast under 400 calories"

This makes 3 LLM calls: requirements, recipe, critique.
"""

import argparse

from app.agents import agents
from app.core.llm import get_llm
from app.core.logging import configure_logging

DEFAULT_REQUEST = ("I am vegetarian, allergic to soy, don't want whey, have paneer, eggs and "
                   "vegetables at home, and want a high-protein dinner under 600 calories.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    args = parser.parse_args()
    configure_logging()
    llm = get_llm()

    print("REQUEST:", args.request, "\n")

    constraints = agents.extract_requirements(args.request, llm)
    print("1. Requirement agent ->")
    print(agents.describe_constraints(constraints), "\n")

    recipe = agents.generate_recipe(constraints, "", llm)
    print("2. Recipe agent ->")
    print(agents.describe_recipe(recipe), "\n")

    report = {"note": "nutrition is calculated in the next phase", "checks": "not run yet"}
    critique = agents.critique_recipe(constraints, recipe, report, llm)
    print("3. Critic agent ->")
    print("problems:", critique.problems or "none")
    print("suggestions:", critique.suggestions or "none")


if __name__ == "__main__":
    main()
