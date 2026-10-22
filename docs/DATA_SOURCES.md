# Public footage and data provenance

ParkWise AI deliberately ships without generated sample metrics or synthetic parking footage. The dashboard is empty until footage is imported and processed.

## Public-source picker

The backend catalogue contains three public Pexels clips, with creator names and source page URLs:

- Tom Fisk, [Aerial Footage Of Cars On A Parking Lot](https://www.pexels.com/video/aerial-footage-of-cars-on-a-parking-lot-3848792/), 38 sec, 3840×2160.
- Yasin Koçtepe, [An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-27832493/), 18 sec, 3840×2160.
- David Pickup, [An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-28125313/), 31 sec, 3840×2160.

The direct MP4 URLs were found by following each Pexels page's free-download link. Their terms and exact links can change; the UI links each source page so the operator can inspect current attribution/licensing conditions. Clips are fetched only on user action and are clearly labeled as recorded stock footage, not live facility streams.

Pexels license: https://www.pexels.com/license/

## Research dataset (not downloaded into this repository)

The [Dragon Lake Parking (DLP) dataset](https://sites.google.com/berkeley.edu/dlp-dataset) from UC Berkeley describes drone footage and annotation data for parking maneuvers, trajectories and agents. Full assets are large (the project website lists 3.5 hours of 4K 25 FPS raw footage; Zenodo records an 8 GB distribution), so this repository does not download or redistribute it. Consult the original dataset page and its current usage conditions before using it for training or publication.

## Recommendations

- For actual operations, use footage from a camera/system the facility controls and has permission to process.
- Keep creator attribution and a copy of the applicable license/version in any redistribution plan.
- Do not claim the Pexels clips represent local traffic volumes, facility inventory, or real-time parking availability.
- For training a bespoke model, record provenance and permissions for each clip and annotation set.
