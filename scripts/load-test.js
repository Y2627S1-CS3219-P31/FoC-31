import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL;
const TOKEN = __ENV.TOKEN;

export const options = {
  stages: [
    { duration: "30s", target: 60 },
    { duration: "90s", target: 60 },
    { duration: "20s", target: 0 },
  ],
};

export default function () {
  const res = http.get(`${BASE_URL}/api/suppliers?page=1&page_size=20`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  check(res, { "status is 200": (r) => r.status === 200 });
}
