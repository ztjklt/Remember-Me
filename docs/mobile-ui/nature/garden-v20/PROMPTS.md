# Garden v20 — image generation record

Date: 2026-10-02

Generated with the built-in imagegen tool. No project API keys, production model adapters or user memory uploads were used. The two flower images are transparent-background edits based on the existing v19 generated macro image; the three portrait garden backgrounds are new images. No stock photographs or third-party artist styles were used.

Assets: `pond.png`, `path.png`, `woodland.png` in this directory; `bloom-cupped.png` and `bloom-side.png` under `assets/brand/forget-me-not/v20/`.

The backgrounds contain no painted fireflies. Glints are a separate, pausable browser layer. These are artistic generated depictions, not field photographs or botanical specimens.

## v20-bg-pond-prompt

Use case: photorealistic-natural
Asset type: portrait 2:3 background photograph for a quiet personal memory garden mobile app
Create a deeply believable, beautiful intimate garden at late dusk, camera low among flowers, looking toward a tiny still pond and a hazy clearing. Soft sage and deep olive trees surround the scene, a few pale wildflowers and fine grasses frame only the lower corners and side edges. A last trace of apricot light falls from the upper left; the pond and clearing carry pale blue grey reflected sky. Natural atmospheric depth: very soft out of focus near leaves in the corners, garden beds in the middle distance, softly receding trees far away. Calm, tender, warm, slightly nostalgic editorial nature photography, fine film texture, not fantasy art.
Crucial layout: the central 65 percent of the width from 25 to 78 percent of image height must be a low detail, softly blurred luminous misty green grey clearing, reserved for an overlaid blue flower. Brightness behind this area around a mid-light muted sage, no central tree trunk, flower, stone or bright light. Upper quarter has a soft uncluttered misty pale evening sky for dark green text. Keep contrast and visual detail at the side margins. Lower sides can be deeper shadowed foliage, so small fireflies added in code will be visible. Portrait full bleed composition, no frame.
Do not include insects, fireflies, sparkle particles, light orbs, lamp strings, lanterns, human figures, buildings, words, interface, blue foreground flowers or giant flowers. No long exposure glowing trails, no fantasy glow, no pitch black night, no sunset sun disk. It should look like a real secluded garden at the end of the day.

## v20-bg-path-prompt

Use case: photorealistic-natural
Asset type: portrait 2:3 photograph used behind a blue flower in a contemplative memory journal mobile app
Scene: an intimate cottage flower garden just after sunset, viewed low at flower height, a narrow old grass path gently bends into a sheltered opening. Ferns, soft moss, fine grasses and a few very small ivory and pale peach blossoms surround the left and right margins. Shadowed fruit trees and shrubs recede naturally in the far distance. The sky is a pale warm apricot grey with cool lilac upper clouds, with no visible sun. It feels safe, quiet, warm and remembered, like returning to a beloved garden on a summer evening.
Composition: central 65 percent kept exceptionally quiet, a softly blurred mid-light muted sage clearing with no focal object between 25 and 80 percent of height, reserved for the application's foreground flower. Upper quarter is low detail and pale enough for dark text. Detailed plants limited to edges and bottom corners, near foliage very softly out of focus. The far garden is layered in delicate atmospheric haze, natural photographic depth rather than uniformly blurred flat scenery.
Style: lifelike editorial garden photography, subtle film grain, lovely restrained light, natural plant shapes and colors. High quality, no painterly rendering, no surreal objects.
Do not include a pond, people, architecture, garden furniture, lanterns, string lights, bright lamps, insects, fireflies, sparkling dust, glowing balls, text or UI. Do not place a large flower in the center. No saturated orange, purple fantasy, pitch black night, fairy-tale lighting or long exposure trails.

## v20-bg-woodland-prompt

Use case: photorealistic-natural
Asset type: portrait 2:3 photographic background for a quiet memory garden on a mobile phone
Scene: a secluded woodland flower garden in the very last blue light of a summer evening. Tall slender trees form a protective canopy at the sides, with deep moss, ferns and small soft ivory wildflowers close to the ground. Through the center there is a hazy blue-sage clearing, illuminated by the last soft reflected sky, with a hint of honey colored light at the distant left horizon. A tranquil sheltered place, intimate rather than grand, warm in feeling even though the color temperature is cooler.
Natural lens depth: lightly blurred close leaves at the corners, modestly detailed side garden beds, softly receding branches and trunks in the distance. Lifelike high-end editorial nature photograph with realistic soft light, no CGI.
Crucial mobile composition: keep the central 65 percent of width from 20 to 82 percent of height low-detail and luminous muted sage-grey, for overlaying one important blue flower. No tree trunk, big flower or object in that zone. Upper quarter can have pale diffuse mist and a sliver of sky, not a dark forest roof, to allow dark green titles. Dense dark foliage sits at left and right edges, with lower dark patches suitable for tiny firefly lights that will be separately animated later. Keep the central background quieter and less contrasty than the margins.
No pond, buildings, people, garden furniture, lamps, lanterns, fireflies, insects, glowing orbs, sparkles, light trails, magical mushrooms, fantasy elements, text, logos, or interface. No giant blue flowers. No theatrical god rays. Calm realistic botanical garden at dusk.

## v20-bloom-left-prompt

Use case: precise-object-edit
Input image: reference and edit target — the supplied generated five-petal forget-me-not blossom, preserve its recognizable dusty blue botanical identity and its five rounded uneven petals.
Create a new lifelike macro photographic view of this blossom with genuine spatial depth: the flower is gently cupped and is turned about 30 degrees away from straight-on toward the LEFT, viewed slightly from above. This must reveal the actual curved petal surfaces and thickness at the front lip, soft mutual shadows between overlapping petals, and a tiny glimpse of the pale green calyx at the rear underside. The near lower petal curls gently toward the camera; the far upper petals recede and are gently foreshortened. All five petals and the tiny warm yellow throat must remain visible and identifiable. It must look like a living three-dimensional flower photographed from a different angle, never a tilted flat photograph or a graphic disk.
Keep one blossom only, no leaves, no long stem, no additional flower. Center the yellow throat close to the center of the square. Entire flower visible with about 8 percent transparent margin. Square 1024 by 1024 composition. Truly transparent background outside the blossom and its tiny calyx.
Lighting: soft warm light from the upper left, cool blue-sage ambient fill, subtle natural rim translucence, delicate internal shadows, all petals sharp enough for a premium macro image. Restrained powder blue, ivory and soft yellow, no neon, no plastic waxy 3D, no stylized illustration, no excessive texture sharpening, no dew, no text. Keep natural slightly asymmetric petals, fine veins and tenderness.

## v20-bloom-side-prompt

Use case: precise-object-edit
Input image is the botanical identity reference: keep a five-petalled blue forget-me-not of the same species and delicate texture, but CHANGE THE CAMERA VIEW substantially.
Make one new ultra-realistic macro photograph of this blossom from a THREE-QUARTER SIDE VIEW. The camera is 50 degrees off the flower's normal axis, looking from the lower RIGHT toward the bloom. The blossom faces upward and LEFT, not straight toward the viewer. The far left petals visibly recede; the near right petal edge projects toward the lens. The petal corolla has a genuine shallow bowl shape, with curved petal folds, overlapping soft shadows, very fine soft fibres and translucent rims. The small golden yellow throat is seen obliquely as an ellipse, not a face-on circle. A small organically curved green calyx and a SHORT 8 mm curved flower stalk are visible behind and below it. Keep all FIVE blue petals visibly present, natural asymmetry and some curling edges.
Full blossom including the short green attachment is centered and fits in a square with transparent breathing room. No long stem, no leaves, no other flowers, no floor. Background must be genuinely transparent.
Lighting: warm soft side light from upper left, cool blue sage reflected ambient light. Silky muted cornflower blue petals, ivory at the throat, warm mellow yellow small center. Fine-art botanical photography with credible dimensional form, not computer-rendered wax or plastic.
Do not just tilt or skew a flat front-facing photo. Do not render the flower front-on. Do not add typography, icons, borders, dew drops, or sparkles.
