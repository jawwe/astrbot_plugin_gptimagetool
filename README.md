# GPT Image Tool

An AstrBot plugin that generates images with an OpenAI-compatible image API.

## Usage

Open the **Settings** Page from the plugin detail page, configure the primary API,
select an image model, then send:

```text
画图 一只戴着宇航员头盔的橘猫，电影级光影
```

The primary API base URL is the complete OpenAI-compatible root, normally ending in
`/v1`. The plugin calls `{base_url}/models` to list models and
`{base_url}/images/generations` to generate images.

## Prompt optimization

Prompt optimization is optional. When enabled, the auxiliary model first calls
`{base_url}/chat/completions` and then the optimized prompt is sent to the image
model. The auxiliary API address and key inherit the primary configuration unless
they are explicitly supplied.

API keys are stored in AstrBot's plugin data directory and are never returned to the
Page after saving.
