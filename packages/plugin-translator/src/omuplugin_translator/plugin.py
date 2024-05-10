from __future__ import annotations

from typing import TypedDict

from edgetrans import EdgeTranslator, Language, Translator
from loguru import logger
from omu.identifier import Identifier
from omuchat import App, Client, model
from omuchat.event.event_types import events
from omuchat.model.content import Component, Root, System, Text

IDENTIFIER = Identifier("cc.omuchat", "translator", "plugin")
APP = App(
    IDENTIFIER,
    version="0.1.0",
)
client = Client(APP)

translator: Translator | None = None


class TrasnlatorConfig(TypedDict):
    active: bool
    languages: list[Language]


config = TrasnlatorConfig(
    active=False,
    languages=["ja", "en"],
)
CONFIG_REGISTRY_TYPE = client.registry.create("config", config)


@CONFIG_REGISTRY_TYPE.listen
async def on_config_change(new_config: TrasnlatorConfig):
    global config
    config = new_config
    logger.info(f"translator config updated: {config}")


async def translate(component: Component, lang: Language) -> Component:
    component = component.copy()
    if not translator:
        return component
    texts = [sibling for sibling in component.iter() if isinstance(sibling, Text)]
    translated = await translator.translate(
        [text.text for text in texts if text.text],
        lang,
    )
    for text, (translation, _) in zip(texts, translated, strict=False):
        text.text = translation
    return component


def is_same_content(a: Component, b: Component) -> bool:
    texts_a = [
        sibling.text.lower() for sibling in a.iter() if isinstance(sibling, Text)
    ]
    texts_b = [
        sibling.text.lower() for sibling in b.iter() if isinstance(sibling, Text)
    ]
    return all(a == b for a, b in zip(texts_a, texts_b, strict=False))


@client.chat.messages.proxy
async def on_message_add(message: model.Message) -> model.Message:
    if not config["active"]:
        return message
    if not message.content:
        return message
    translations: dict[str, Component] = {}
    if len(config["languages"]) == 1:
        lang = config["languages"][0]
        translated = await translate(message.content, lang)
        message.content = translated
        return message
    for lang in config["languages"]:
        translated = await translate(message.content, lang)
        translations[lang] = translated
    if all(
        is_same_content(translations[lang], translations[config["languages"][0]])
        for lang in config["languages"][1:]
    ):
        message.content = translations[config["languages"][0]]
        return message
    content = Root()
    for i, (lang, translated) in enumerate(translations.items()):
        lines = [
            Text(f"{lang}:") if i == 0 else Text(f" {lang}:"),
            translated,
        ]
        content.add(System(lines))
    message.content = content
    return message


@client.on(events.ready)
async def on_ready():
    global translator, config
    config = await CONFIG_REGISTRY_TYPE.get()
    translator = await EdgeTranslator.create()


if __name__ == "__main__":
    client.run()
