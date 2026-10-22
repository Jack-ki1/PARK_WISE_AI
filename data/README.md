# Runtime data directory

`uploads/`, `previews/`, and `processed/` are empty in the source archive by design. No generated or fabricated parking footage is included. The application writes operator uploads and explicitly fetched public clips here at runtime; Docker uses the `parkwise_data` volume.
