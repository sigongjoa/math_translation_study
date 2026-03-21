import fitz
import json

def get_toc():
    doc = fitz.open("PCM.pdf")
    toc = doc.get_toc()
    
    # Each entry in toc is [level, title, page]
    # page is 1-indexed
    
    total_pages = len(doc)
    
    # Process TOC to include page ranges
    processed_toc = []
    for i in range(len(toc)):
        level, title, page = toc[i]
        
        # Find next page number at the same or higher level (smaller number) to determine end of current section
        end_page = total_pages
        for j in range(i + 1, len(toc)):
            next_level, next_title, next_page = toc[j]
            if next_level <= level:
                end_page = next_page - 1
                break
        
        processed_toc.append({
            "level": level,
            "title": title,
            "start_page": page,
            "end_page": end_page,
            "page_count": end_page - page + 1
        })
    
    doc.close()
    return processed_toc

if __name__ == "__main__":
    toc_data = get_toc()
    print(json.dumps(toc_data, indent=2))
