import sys
from pathlib import Path
# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from pcm.core.json_to_latex import generate_full_document
import shutil

def build_pdf(output_dir, part_label):
    print(f"\n--- Generating PDF for {output_dir} ({part_label}) ---")
    sections_dir = Path(output_dir) / "sections"
    latex_dir = Path(output_dir) / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy images to latex directory if they exist
    images_src = Path(output_dir) / "images"
    images_dst = latex_dir / "images"
    if images_src.exists():
        if images_dst.exists():
            shutil.rmtree(images_dst)
        shutil.copytree(images_src, images_dst)

    tex_file = latex_dir / "main.tex"
    
    # Check if any JSON files exist
    if not any(sections_dir.glob("*.json")):
        print(f"No JSON sections found in {sections_dir}")
        return

    generate_full_document(
        sections_dir=str(sections_dir),
        output_tex=str(tex_file),
        part_label=part_label
    )
    
    if tex_file.exists():
        for run in range(2):
            print(f"  XeLaTeX run {run+1}...")
            subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "main.tex"],
                cwd=str(latex_dir),
                capture_output=True, text=True
            )
        
        pdf_file = latex_dir / "main.pdf"
        if pdf_file.exists():
            final_pdf = f"preview_{output_dir}.pdf"
            shutil.copy2(pdf_file, final_pdf)
            print(f"Success! {final_pdf} created.")
        else:
            print(f"Failed to generate PDF for {output_dir}")

if __name__ == "__main__":
    build_pdf("output_part_02", "II")
    build_pdf("output_part_03", "III")
