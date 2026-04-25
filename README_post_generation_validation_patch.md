# post-generation validation + targeted regeneration patch

## added
- `app/validation/post_generation_repair.py`
  - validates every generated file in `created` + `overwritten`
  - runs project-wide Java import fix first
  - records invalid files and reasons
  - can regenerate only invalid files and re-apply them
  - writes `.autopj_debug/post_generation_validation.json`

## integrated
- `app/ui/main_window.py`
  - batch Ollama flow now runs post-generation validation automatically after `apply_report.json`
  - invalid files are regenerated once using the original per-file spec
  - final validation summary is stored in `report["patched"]["post_generation_validation"]`
- legacy single-shot apply path also runs validation, but without regeneration callback

## behavior
1. generate files
2. write files
3. run import fixer
4. validate all generated files
5. if invalid file exists:
   - analyze reason
   - regenerate that file once
   - re-apply
   - validate again
6. save final report

## validation scope
- generated files only (`created`, `overwritten`)
- file-level syntax/content validation via existing `validate_generated_content`
- Java import correction before and after targeted regeneration
