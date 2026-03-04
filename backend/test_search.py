from ddgs import DDGS

try:
    print("Testing DDGS web search...")
    with DDGS() as ddgs:
        results = list(ddgs.text('Azure RDP troubleshooting', max_results=5))
        print(f"Found {len(results)} results")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('title', 'No title')}")
            print(f"   URL: {r.get('href', 'No URL')}")
            print(f"   Snippet: {r.get('body', 'No snippet')[:100]}...")
            print()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
