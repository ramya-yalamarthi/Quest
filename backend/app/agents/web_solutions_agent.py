
# """
# WebSolutions Agent
# Searches public websites for similar discussions and resolutions to support tickets.
# Uses Bing Search API to find relevant content across legitimate sources.
# """


# import logging
# from typing import List, Dict, Optional
# from app.utils.llm import LLMClient



# class WebSolutionsAgent:
#     """Agent responsible for finding web-based solutions by searching across
#     public legitimate websites including Microsoft Learn, TechCommunity,
#     Stack Overflow, Reddit, GitHub Issues, and other forums."""


#     def __init__(self):
#         self._logger = logging.getLogger(__name__)
#         self._llm = LLMClient()


#     def find_solutions(
#         self,
#         ticket_title: str,
#         ticket_description: str,
#         max_results: int = 5,
#     ) -> List[Dict[str, str]]:
#         """
#         Search the web for similar discussions and resolutions.
#         
#         Args:
#             ticket_title: Title of the support ticket
#             ticket_description: Description of the issue
#             max_results: Maximum number of solutions to return
#             
#         Returns:
#             List of dictionaries containing:
#             - title: Title of the solution/discussion
#             - url: Link to the source
#             - steps: List of actionable steps (if applicable)
#             - summary: Brief summary of the resolution
#         """
#         try:
#             # Build optimized search query
#             search_query = self._build_search_query(ticket_title, ticket_description)
#             self._logger.info(f"Web search query: {search_query}")
#             
#             # Perform web search
#             search_results = self._perform_web_search(search_query, count=max_results * 2)
#             
#             if not search_results:
#                 self._logger.warning("No web search results found")
#                 return []
#             
#             # Filter and rank results using LLM
#             relevant_results = self._filter_relevant_results(
#                 search_query,
#                 ticket_title,
#                 ticket_description,
#                 search_results,
#                 max_results
#             )
#             
#             # Extract solutions from relevant results
#             solutions = []
#             for result in relevant_results[:max_results]:
#                 solution = self._extract_solution(
#                     ticket_title,
#                     ticket_description,
#                     result
#                 )
#                 if solution:
#                     solutions.append(solution)
#             
#             self._logger.info(f"Found {len(solutions)} web solutions")
#             return solutions
#             
#         except Exception as e:
#             self._logger.error(f"Error finding web solutions: {e}", exc_info=True)
#             return []


#     def _build_search_query(self, title: str, description: str) -> str:
#         """Use LLM to build an optimized search query."""
#         prompt = f"""You are a search query optimizer for technical support issues.
# Given a support ticket, create an optimized web search query that will find similar discussions and resolutions.
# 
# Guidelines:
# - Extract key technical terms, error messages, product names
# - Remove filler words and personal context
# - Include relevant synonyms or related terms
# - Keep it concise (max 10-15 words)
# - Focus on the core problem, not the user's specific environment
# 
# Ticket Title: {title}
# Ticket Description: {description}
# 
# Return only the optimized search query, nothing else."""
# 
#         query = self._llm.complete(
#             system_prompt="You are a search query optimization expert.",
#             user_prompt=prompt,
#             temperature=0.3,
#             max_tokens=100
#         )
#         
#         return query.strip().strip('"').strip("'")


#     def _perform_web_search(self, query: str, count: int = 10) -> List[Dict[str, str]]:
#         """
#         Perform web search using Bing Search API.
#         Falls back to alternative methods if API is not available.
#         """
#         # Import here to avoid circular dependency
#         from app.utils.websearch import search_web
#         
#         return search_web(query, count=count)


#     def _filter_relevant_results(
#         self,
#         search_query: str,
#         ticket_title: str,
#         ticket_description: str,
#         search_results: List[Dict[str, str]],
#         max_results: int
#     ) -> List[Dict[str, str]]:
#         """Use LLM to filter and rank search results by relevance."""
#         
#         if not search_results:
#             self._logger.info("No search results to filter")
#             return []
#         
#         self._logger.info(f"Filtering {len(search_results)} search results")
#         
#         # If we have few results, skip filtering and return all
#         if len(search_results) <= max_results:
#             self._logger.info(f"Returning all {len(search_results)} results (no filtering needed)")
#             return search_results
#         
#         # Format results for LLM
#         results_text = "\n\n".join([
#             f"Result {i+1}:\nTitle: {r.get('title', 'N/A')}\nURL: {r.get('url', 'N/A')}\nSnippet: {r.get('snippet', 'N/A')}"
#             for i, r in enumerate(search_results[:15])  # Limit to avoid token overflow
#         ])
#         
#         prompt = f"""You are a technical support expert evaluating web search results.
# Given a support ticket and web search results, identify which results are most likely to contain relevant solutions or discussions.
# 
# Ticket Title: {ticket_title}
# Ticket Description: {ticket_description}
# 
# Search Results:
# {results_text}
# 
# Evaluate each result based on:
# 1. Relevance to the specific issue described
# 2. Likelihood of containing actionable solutions
# 3. Source legitimacy (official docs, community forums, technical blogs)
# 4. Technical depth and specificity
# 
# Return ONLY the numbers of the {max_results} most relevant results, separated by commas (e.g., "1,3,7,9,12").
# If fewer than {max_results} are relevant, list only the relevant ones.
# Be inclusive - if a result might be somewhat relevant, include it."""
# 
#         try:
#             response = self._llm.complete(
#                 system_prompt="You are an expert at evaluating technical content relevance.",
#                 user_prompt=prompt,
#                 temperature=0.2,
#                 max_tokens=100
#             )
#             
#             self._logger.debug(f"LLM filtering response: {response}")
#             
#             # Parse the response to get result indices
#             indices = [int(x.strip()) - 1 for x in response.strip().split(",") if x.strip().isdigit()]
#             relevant = [search_results[i] for i in indices if 0 <= i < len(search_results)]
#             
#             if relevant:
#                 self._logger.info(f"LLM selected {len(relevant)} relevant results")
#                 return relevant
#             else:
#                 self._logger.warning("LLM filtering returned no results, using top results instead")
#                 return search_results[:max_results]
#                 
#         except Exception as e:
#             self._logger.warning(f"Failed to filter with LLM: {e}, returning top {max_results} results")
#             return search_results[:max_results]


#     def _extract_solution(
#         self,
#         ticket_title: str,
#         ticket_description: str,
#         result: Dict[str, str]
#     ) -> Optional[Dict[str, str]]:
#         """Extract solution information from a search result."""
#         
#         url = result.get("url", "")
#         title = result.get("title", "")
#         snippet = result.get("snippet", "")
#         
#         if not url:
#             self._logger.debug("Skipping result with no URL")
#             return None
#         
#         self._logger.info(f"Extracting solution from: {url}")
#         
#         # Fetch full content if possible
#         content = snippet
#         try:
#             from app.utils.websearch import fetch_page_content
#             full_content = fetch_page_content(url, max_length=3000)
#             if full_content and len(full_content) > len(snippet):
#                 content = full_content
#                 self._logger.debug(f"Fetched {len(content)} chars from page")
#         except Exception as e:
#             self._logger.debug(f"Could not fetch full content from {url}: {e}, using snippet")
#         
#         if not content or len(content.strip()) < 50:
#             self._logger.debug(f"Insufficient content from {url}")
#             return None
#         
#         # Use LLM to extract solution steps
#         prompt = f"""You are a technical support assistant extracting solution information.
# Given a support ticket and content from a web page, extract the key solution or resolution if present.
# 
# Ticket Title: {ticket_title}
# Ticket Description: {ticket_description}
# 
# Web Content:
# {content[:3000]}
# 
# Extract:
# 1. A brief summary (1-2 sentences) of how this content relates to the issue
# 2. Actionable steps if present (max 6 steps)
# 
# Format your response as:
# Summary: [your summary]
# Steps:
# - [step 1]
# - [step 2]
# ...
# 
# If there are no clear steps but the content is relevant, just provide the summary.
# Only respond with "Not relevant" if the content is completely unrelated to the ticket."""
# 
#         try:
#             response = self._llm.complete(
#                 system_prompt="You are an expert at extracting technical solutions from documentation.",
#                 user_prompt=prompt,
#                 temperature=0.2,
#                 max_tokens=400
#             )
#             
#             self._logger.debug(f"LLM extraction response: {response[:200]}...")
#             
#             if "not relevant" in response.lower().strip():
#                 self._logger.debug(f"LLM deemed content not relevant for {url}")
#                 return None
#             
#             # Parse the response
#             summary = ""
#             steps = []
#             
#             lines = response.strip().split("\n")
#             current_section = None
#             
#             for line in lines:
#                 stripped = line.strip()
#                 if not stripped:
#                     continue
#                 
#                 if stripped.lower().startswith("summary:"):
#                     current_section = "summary"
#                     summary = stripped.split(":", 1)[1].strip()
#                 elif stripped.lower().startswith("steps:"):
#                     current_section = "steps"
#                 elif stripped.startswith("-") and current_section == "steps":
#                     step = stripped.lstrip("- ").strip()
#                     if step:
#                         steps.append(step)
#                 elif current_section == "summary" and not stripped.lower().startswith("steps:"):
#                     summary += " " + stripped
#             
#             solution = {
#                 "title": title or "Web Solution",
#                 "url": url,
#                 "summary": summary.strip() or "Relevant discussion found",
#                 "steps": steps
#             }
#             
#             self._logger.info(f"Extracted solution with {len(steps)} steps from {url}")
#             return solution
#             
#         except Exception as e:
#             self._logger.error(f"Error extracting solution from {url}: {e}", exc_info=True)
#             # Return basic solution even if extraction fails
#             return {
#                 "title": title or "Web Solution",
#                 "url": url,
#                 "summary": snippet[:200] if snippet else "Relevant resource found",
#                 "steps": []
#             }
