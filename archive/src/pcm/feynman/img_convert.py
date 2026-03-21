import os
import cairosvg

def convert_svg_to_pdf(svg_path, pdf_path):
    """Convert SVG/SVGZ to PDF using cairosvg."""
    try:
        cairosvg.svg2pdf(url=svg_path, write_to=pdf_path)
        return True
    except Exception as e:
        print(f'[ERR] cairosvg failed for {svg_path}: {e}')
        return False

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: python3 feynman_img_convert.py input.svgz output.pdf')
    else:
        ok = convert_svg_to_pdf(sys.argv[1], sys.argv[2])
        print('[OK]' if ok else '[FAIL]')