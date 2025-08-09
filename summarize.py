from llm_utils import ollama_summarize


if __name__ == "__main__":
    sample = (
        "The team met on Tuesday to discuss the new app features. "
        "Action items: John will implement OAuth login, Sarah will update the dashboard UI."
    )
    print(ollama_summarize(sample))

