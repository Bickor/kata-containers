# syntax=docker/dockerfile:1.7
FROM rust:1.95-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends clang gcc git libseccomp-dev make pkg-config protobuf-compiler && rm -rf /var/lib/apt/lists/*
ENV CARGO_BUILD_JOBS=8 CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0
ARG KATA_COMMIT
RUN git clone --no-checkout https://github.com/Bickor/kata-containers.git /src && git -C /src checkout "${KATA_COMMIT}"
WORKDIR /src
RUN make -C src/runtime-rs BUILD_TYPE=release LIBC=gnu USE_BUILTIN_DB=false HYPERVISOR=clh-runtime-rs runtime
RUN cargo test --manifest-path src/runtime-rs/Cargo.toml -p resource --lib smb_volume -- --nocapture
# Keep the guest agent compatible with the managed Azure Linux 3.32 guest.
# ce08dce already includes the snapshot-demo restore backport (fork PR #1).
RUN git clone --no-checkout https://github.com/Bickor/kata-containers.git /agent \
    && git -C /agent checkout ce08dce9739bdd4dc531f245afeb81a3b721dfaa \
    && git show 1f06aaa15 -- src/agent/src/storage/fs_handler.rs src/agent/src/storage/mod.rs src/libs/kata-types/src/device.rs | git -C /agent apply
RUN make -C /agent/src/agent BUILD_TYPE=release LIBC=gnu src/version.rs \
    && make -C /agent/src/agent BUILD_TYPE=release LIBC=gnu optimize \
    && strip /src/target/x86_64-unknown-linux-gnu/release/containerd-shim-kata-v2 /agent/target/x86_64-unknown-linux-gnu/release/kata-agent
FROM akssbxheberlingsnaacrsht774mnb6xzi.azurecr.io/runtime/kata-v2-installer@sha256:452bd4af5a5832b525f5e9b7f4d057b04f42f5ab5d226326f8ec8fe0a7f39a71
USER root
ARG KATA_COMMIT
LABEL org.opencontainers.image.source="https://github.com/Bickor/kata-containers" org.opencontainers.image.revision="${KATA_COMMIT}"
COPY --from=builder /src/target/x86_64-unknown-linux-gnu/release/containerd-shim-kata-v2 /payload/containerd-shim-kata-v2
COPY --from=builder /agent/target/x86_64-unknown-linux-gnu/release/kata-agent /payload/kata-agent
ENTRYPOINT ["/bin/bash"]
