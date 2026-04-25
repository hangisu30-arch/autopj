from __future__ import annotations

from pathlib import Path


def build_targeted_regen_prompt(path: str, purpose: str, spec: str, reason: str, repair_code: str = '') -> str:
    name = Path(path or '').name
    bullets = [
        'Your previous output for this file was invalid. Regenerate ONLY this file content.',
        'Output ONLY the file content. No JSON. No markdown. No explanation. No code fences.',
        'Do NOT output any path comment line.',
        f'Target file path: {path}',
        f'Failure reason: {reason or "unknown"}',
    ]
    if repair_code:
        bullets.append(f'Repair code: {repair_code}')

    low = (reason or '').lower()
    if name.endswith('.java'):
        bullets.extend([
            'Java file must contain a valid package declaration and a matching public type declaration.',
            'Do not emit shell syntax, pseudo-code, JSON, or markdown.',
        ])
    if name.endswith('Mapper.xml') or name.endswith('.xml'):
        bullets.extend([
            'XML must be well-formed and contain the expected root element only.',
            'Do not emit Spring beans XML unless the spec explicitly asks for it.',
        ])
    if name.endswith('.jsp'):
        bullets.extend([
            'JSP must be placed under the correct WEB-INF/views domain path and contain real JSP/HTML tags.',
            'Return-compatible view naming must stay aligned with the target JSP file name.',
        ])
    if name.endswith('.jsx') or name.endswith('.js'):
        bullets.extend([
            'React files must use React syntax only. No Angular/Nest decorators or constructor(private ...) syntax.',
            'Import paths must match the standardized React plan paths.',
        ])
    if 'unsupported package' in low:
        bullets.append('Remove unsupported imports and keep only allowed runtime imports for this file.')
    if 'missing route' in low or 'route' in low:
        bullets.append('Ensure route constants and registry usage stay aligned with the react plan.')

    return (
        "\n".join(bullets)
        + "\n\n[FILE PURPOSE]\n"
        + (purpose or 'generated')
        + "\n\n[FILE SPEC FROM GEMINI]\n"
        + (spec or '')
    )
