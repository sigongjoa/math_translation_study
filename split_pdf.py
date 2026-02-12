#!/usr/bin/env python3
import fitz
import os
from pathlib import Path

def split_pdf(input_path: str, pages_per_chunk: int = 40):
    output_dir = Path("PCM_split")
    output_dir.mkdir(exist_ok=True)
    
    doc = fitz.open(input_path)
    total_pages = len(doc)
    
    chunk_count = (total_pages + pages_per_chunk - 1) // pages_per_chunk
    
    print(f"Total pages: {total_pages}")
    print(f"Splitting into {chunk_count} chunks...")
    
    for i in range(chunk_count):
        start_page = i * pages_per_chunk
        end_page = min((i + 1) * pages_per_chunk, total_pages)
        
        # Output filename: PCM_part_01_pages_1_40.pdf
        part_num = i + 1
        output_filename = f"PCM_part_{part_num:02d}_pages_{start_page + 1}_{end_page}.pdf"
        output_path = output_dir / output_filename
        
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)
        new_doc.save(str(output_path))
        new_doc.close()
        
        print(f"Saved: {output_filename}")
    
    doc.close()
    print("\nSplitting complete!")

if __name__ == "__main__":
    split_pdf("PCM.pdf", 40)
