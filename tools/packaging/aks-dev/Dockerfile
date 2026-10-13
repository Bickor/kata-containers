# syntax=docker/dockerfile:1.7
FROM rust:1.95-bookworm@sha256:6258907abe69656e41cd992e0b705cdcfabcbbe3db374f92ed2d47121282d4a1 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang gcc git libseccomp-dev libssl-dev make pkg-config protobuf-compiler python3 \
    && rm -rf /var/lib/apt/lists/*
ENV CARGO_BUILD_JOBS=8 CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0
WORKDIR /src
COPY . .
ARG SOURCE_COMMIT
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/src/target \
    bash tools/packaging/aks-dev/build.sh "${SOURCE_COMMIT}"
FROM scratch AS artifacts
COPY --from=builder /out/ /
