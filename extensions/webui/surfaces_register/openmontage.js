export default function register(surfaces) {
  surfaces.registerSurface({ id: "openmontage", title: "OpenMontage", icon: "movie", order: 62,
    modalPath: "/plugins/openmontage/webui/main.html", open() {}, close() {} });
}
