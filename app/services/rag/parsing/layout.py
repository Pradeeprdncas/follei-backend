import fitz

def extract_layout(pdf_path):

    doc = fitz.open(pdf_path)

    hierarchy = []

    current_h1 = None
    current_h2 = None
    current_h3 = None

    for page_number in range(len(doc)):

        page = doc[page_number]

        blocks = page.get_text("dict")["blocks"]

        for block in blocks:

            if "lines" not in block:
                continue

            for line in block["lines"]:

                text = "".join(
                    span["text"]
                    for span in line["spans"]
                ).strip()

                if not text:
                    continue

                font_size = max(
                    span["size"]
                    for span in line["spans"]
                )

                if font_size >= 20:

                    current_h1 = text
                    current_h2 = None
                    current_h3 = None

                    continue

                elif font_size >= 16:

                    current_h2 = text
                    current_h3 = None

                    continue

                elif font_size >= 13:

                    current_h3 = text

                    continue

                hierarchy.append(
                    {
                        "page": page_number + 1,

                        "h1": current_h1,

                        "h2": current_h2,

                        "h3": current_h3,

                        "section_path": [
                            x for x in
                            [
                                current_h1,
                                current_h2,
                                current_h3
                            ]
                            if x
                        ],

                        "text": text
                    }
                )

    return hierarchy