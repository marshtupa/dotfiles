#!/usr/bin/env python3
import argparse
import mimetypes
import pathlib

from google.cloud import documentai
from google.protobuf.field_mask_pb2 import FieldMask

def main():
    ap = argparse.ArgumentParser(description="Send file to Document AI OCR and save only text to .md")
    ap.add_argument("input_path", help="Path to image/PDF")
    args = ap.parse_args()

    endpoint = "eu-documentai.googleapis.com"
    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": endpoint}
    )

    name = client.processor_path(777922642538, "eu", "69ba1e09ce176998")

    in_path = pathlib.Path(args.input_path)
    content = in_path.read_bytes()
    mime_type, _ = mimetypes.guess_type(str(in_path))
    if not mime_type:
        mime_type = "application/pdf" if in_path.suffix.lower() == ".pdf" else "image/jpeg"

    raw_document = documentai.RawDocument(content=content, mime_type=mime_type)

    # Возвращаем только текст и отключаем картинки в ответе
    field_mask = FieldMask(paths=["text"])
    request = documentai.ProcessRequest(
        name=name,
        raw_document=raw_document,
        field_mask=field_mask,
        imageless_mode=True,
    )

    result = client.process_document(request=request)
    text = (result.document.text or "").strip() + "\n"

    out_path = pathlib.Path(in_path.with_suffix(".md"))
    out_path.write_text(text, encoding="utf-8")
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()