"""Le o OpenAPI do proprio backend e descreve o que cada rota aceita.

Escrever o catalogo na mao envelheceria em uma semana: campo novo, campo que
virou obrigatorio, enum que ganhou opcao. O `drf-spectacular` ja publica isso
em `/api/schema/`, entao o gerador de payload e as mutacoes saem da fonte
verdadeira — e um campo novo entra no teste sozinho.
"""
import json

SKIP_FIELDS = {"id", "account", "created_at", "updated_at", "created_by", "updated_by", "deleted_at"}

#: Campo de arquivo so viaja em multipart. Mandado como texto em JSON, ele
#: devolve 400 sempre — ruido puro, nao informacao sobre o sistema.
FILE_SUFFIXES = ("_upload", "_uploads", "_file", "_image_file")
FILE_FIELDS = {"image", "logo", "photo", "picture", "avatar", "file", "attachment", "icon"}


class EndpointSchema:
    """O contrato de escrita de uma rota: campos, tipos e obrigatorios."""

    def __init__(self, path, method, fields=None, required=None, name=""):
        self.path = path
        self.method = method
        self.fields = fields or {}
        self.required = required or []
        self.name = name or path

    def __repr__(self):
        return f"<EndpointSchema {self.method} {self.path} campos={len(self.fields)}>"

    @property
    def writable(self):
        return {f: m for f, m in self.fields.items() if f not in SKIP_FIELDS}


def _resolve(node, components, depth=0):
    """Segue $ref/allOf ate um objeto com `properties`."""
    if not isinstance(node, dict) or depth > 6:
        return {}
    if "$ref" in node:
        key = node["$ref"].rsplit("/", 1)[-1]
        return _resolve(components.get(key, {}), components, depth + 1)
    if "allOf" in node:
        merged = {"properties": {}, "required": []}
        for part in node["allOf"]:
            resolved = _resolve(part, components, depth + 1)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"].extend(resolved.get("required", []))
            for chave in ("type", "format", "enum", "maxLength", "nullable"):
                if chave in resolved and chave not in merged:
                    merged[chave] = resolved[chave]
        return merged
    if node.get("oneOf"):
        # O primeiro ramo com `enum` de verdade vence; `BlankEnum` ("") sozinho
        # nao descreve nada, e escolher ele apagaria as opcoes reais do campo.
        ramos = [_resolve(ramo, components, depth + 1) for ramo in node["oneOf"]]
        com_valores = [r for r in ramos if len(r.get("enum") or []) > 1] or ramos
        combinado = dict(com_valores[0])
        combinado["enum"] = [v for r in ramos for v in (r.get("enum") or []) if v not in ("", None)]
        return combinado
    return node


def _field_meta(spec, components):
    # Um enum do drf-spectacular chega como `oneOf: [$ref Enum, $ref BlankEnum]`.
    # Sem seguir o oneOf, o campo perde tipo E lista de valores: o gerador manda
    # texto livre num choice e o 400 resultante seria culpa do teste.
    if any(chave in spec for chave in ("$ref", "allOf", "oneOf")):
        resolvido = _resolve(spec, components)
        spec = {**resolvido, **{k: v for k, v in spec.items() if k not in ("$ref", "allOf", "oneOf")}}
    meta = {
        "type": spec.get("type"),
        "format": spec.get("format"),
        "max_length": spec.get("maxLength"),
        "pattern": spec.get("pattern"),
        "enum": spec.get("enum") or (spec.get("items", {}) or {}).get("enum"),
        "nullable": bool(spec.get("nullable")),
        "read_only": bool(spec.get("readOnly")),
        "items": spec.get("items"),
        "default": spec.get("default"),
    }
    if meta["type"] is None and meta["enum"]:
        meta["type"] = "string"
    return meta


class ApiSchema:
    """Todas as rotas de escrita conhecidas, indexadas por (metodo, caminho)."""

    def __init__(self, document):
        self.document = document
        self.components = (document.get("components") or {}).get("schemas") or {}
        self.endpoints = {}
        self._load()

    @classmethod
    def fetch(cls, client, headers=None):
        response = client.request("GET", "/api/schema/?format=json", headers=headers)
        if response.status != 200:
            raise RuntimeError(f"nao consegui ler /api/schema/ (HTTP {response.status}) {response.excerpt()}")
        return cls(json.loads(response.body.decode("utf-8")))

    def _load(self):
        for path, operations in (self.document.get("paths") or {}).items():
            for method, operation in operations.items():
                if method.upper() not in ("POST", "PUT", "PATCH"):
                    continue
                body = ((operation.get("requestBody") or {}).get("content") or {}).get("application/json")
                if not body:
                    continue
                resolved = _resolve(body.get("schema") or {}, self.components)
                properties = resolved.get("properties") or {}
                fields = {}
                for name, spec in properties.items():
                    meta = _field_meta(spec if isinstance(spec, dict) else {}, self.components)
                    if meta["read_only"] or name in SKIP_FIELDS:
                        continue
                    if meta["format"] == "binary" or name.endswith(FILE_SUFFIXES) or name in FILE_FIELDS:
                        continue
                    fields[name] = meta
                self.endpoints[(method.upper(), path)] = EndpointSchema(
                    path=path,
                    method=method.upper(),
                    fields=fields,
                    required=[r for r in (resolved.get("required") or []) if r in fields],
                    name=operation.get("operationId", path),
                )

    def for_endpoint(self, method, path):
        """Aceita `/api/v1/customers/` e devolve o schema, ou um vazio."""
        found = self.endpoints.get((method.upper(), path))
        if found:
            return found
        for (candidate_method, candidate_path), schema in self.endpoints.items():
            if candidate_method == method.upper() and candidate_path.rstrip("/") == path.rstrip("/"):
                return schema
        return EndpointSchema(path, method.upper())

    def creatable_paths(self):
        """Rotas POST de colecao (as que criam registro), sem actions."""
        found = []
        for (method, path), schema in sorted(self.endpoints.items()):
            if method != "POST" or "{" in path:
                continue
            if not schema.fields:
                continue
            found.append(path)
        return found
