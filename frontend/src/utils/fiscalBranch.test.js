import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from "../services/api";
import { resolveBranchIdForRestaurant } from "./fiscalBranch";

describe("resolveBranchIdForRestaurant", () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it("acha a filial cujo restaurant bate com o id informado", async () => {
    api.get.mockResolvedValue({
      data: {
        results: [
          { id: "branch-1", restaurant: "rest-a" },
          { id: "branch-2", restaurant: "rest-b" },
        ],
      },
    });

    const branchId = await resolveBranchIdForRestaurant("rest-b");

    expect(branchId).toBe("branch-2");
    expect(api.get).toHaveBeenCalledWith(
      "/branches/",
      expect.objectContaining({ params: { page_size: 200 }, skipRestaurantScope: true }),
    );
  });

  it("devolve null quando nenhuma filial pertence ao restaurante", async () => {
    api.get.mockResolvedValue({ data: { results: [{ id: "branch-1", restaurant: "rest-a" }] } });

    const branchId = await resolveBranchIdForRestaurant("rest-z");

    expect(branchId).toBeNull();
  });

  it("devolve null quando a lista vem vazia", async () => {
    api.get.mockResolvedValue({ data: { results: [] } });

    expect(await resolveBranchIdForRestaurant("rest-a")).toBeNull();
  });
});
