from typing import List, TypedDict


class InvalidationId(TypedDict):
    objectSource: int
    objectId: str
    topic: str
    subscribeToGcmTopics: bool
    protoCreationTimestampMs: str


class InvalidationContinuationData(TypedDict):
    invalidationId: InvalidationId
    timeoutMs: int
    continuation: str
    clickTrackingParams: str


class ContinuationsItem(TypedDict):
    invalidationContinuationData: InvalidationContinuationData


type Continuations = List[ContinuationsItem]


class TimedContinuationData(TypedDict):
    timeoutMs: int
    continuation: str


class Continuation(TypedDict):
    timedContinuationData: TimedContinuationData
