# Diary presets implementation and local release

Implemented: `diary_presets` Django app, immutable JSON version snapshots, editable drafts, series/template/page administration, protected STS multipart upload sessions, independent OSS-region processing worker, download plans pinned to versions, per-plan signed resource URLs, workstation publication and live verification commands. Resource bytes do not pass through API views. New template objects are private even when the existing bucket has public-read defaults.

Current database implementation stores each version's indexed manifest/pages/file dependencies in a JSON snapshot rather than normalizing every immutable file/page into a separate row. Uploads, publication events and download leases are relational records. This keeps the first implementation transactional; larger catalogs will require pagination/index normalization. Catalog currently caps at 500 books.

Backend requirements: `pip install -r requirements.txt`, `python manage.py migrate diary_presets`. Configure existing ALIYUN_* environment values plus `DIARY_PRESETS_UPLOAD_ROLE_ARN` and a randomly generated `DIARY_PRESETS_PROCESSOR_TOKEN` for the independent worker. Never commit credentials. Browser direct upload requires OSS CORS for the admin origin and multipart methods.

Web route: `/diary-presets` in existing backoffice-web. Single-page uploads must contain exactly one page in the regular `.diarypreset.zip` format. Ordering/deletion/title changes are saved as a new version. Local frontend default: http://localhost:6018/diary-presets.

Worker deployment: `deployment/preset-processor/README.md`. It is not enabled on the low-bandwidth API server. A dedicated same-region compute worker must be provisioned before browser uploads can leave the queued state; the workstation command below can publish immediately without it. Cloud worker provisioning/production release has not been performed by this change.

Workstation direct publication:

```sh
python manage.py publish_diary_preset /path/to/book.diarypreset.zip \
  --series islands --series-title 海岛系列 --title 舟山 \
  --template-id <stable-uuid> --report /path/to/publication.json
python manage.py verify_diary_preset <stable-uuid> --report /path/to/verification.json
```

The publisher reads local bytes, validates, uploads content-addressed private blobs directly to OSS, writes a version manifest and registers the snapshot in the connected database. Identical archive reruns are idempotent. The verifier checks all resource lengths, downloads the first page's dependencies and verifies hashes, checks HTTP Range and anonymous denial.

Client: `PresetDownloadManager` and `RemotePresetLibraryScreen`, configured by AppContainer. Entry is “云端预设与下载管理” in the existing preset library. Three concurrent business tasks share file locks/cache; completed 8 MiB ranges persist and resume with newly signed URLs. Task state is stored in Application Support JSON (not SQLite in this first implementation). Downloaded single-page subset manifests are compatible with the existing importer. Whole books are imported once atomically. No background-session execution guarantee; paused/interrupted tasks resume manually after restart. Current cache has no LRU UI, and remote catalog has no persistent offline directory fallback yet; local Bundle presets and already imported books remain available.

Validation: backend domain/auth/version/plan tests, web production build and iOS simulator build. Actual background behavior, UI interaction, and canvas rendering on a device require separate device acceptance. Automated success does not imply visual equivalence to Photoshop.


## Zhoushan source conversion (2026-10-16)

63 selected pages, 585 content objects, 493 image assets, 1267 indexed runtime files. Original package indexed bytes: 389371905; ZIP bytes: 390158170. Stable database template UUID: 21a8759e-e59f-58a0-b92e-86d41d88848a. Series: islands. Source and exclusion decisions: zhoushan-source-selection.json.

Opening order is cover, opening spread left, opening spread right. Remaining pages are paired left-before-right. Newer v02/v2 versions selected; Shengshan first edition selected over initial drafts. Intermediate Gouqi “待Logo” PSD excluded. Photo-wall Putuo layouts retained as distinct compositions.

Known conversion limitations: 468 root layers, zero detected native editable text/photo slots; 24 smart objects rasterized; 27 dissolve effects approximated with fixed random sampling. Source masks are baked into relevant image alpha; one lighterColor blend approximated as lighten. Detailed source report remains beside the exported package. These are not verified pixel-equivalent iOS renderings.
