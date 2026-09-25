"""O preço do produto, que sai de cálculo e não de coluna.

Vive fora de `models.py` porque é UMA responsabilidade, e a mais consultada de
todas: quem abre o cadastro do produto procurando "de onde vem o preço" acha
aqui, em quarenta linhas, em vez de garimpar entre oitenta campos de estoque,
fiscal e produção.

O que o produto guarda é `base_price` e `base_promotional_price` — valores de
referência, que nenhuma promoção toca. O que ele RESPONDE passa por aqui.
"""


class ProductPricing:
    # ------------------------------------------------------------------
    # O PREÇO, DINÂMICO.
    #
    # Os nomes são os de sempre de propósito: o formulário, os dois PDVs, o
    # cardápio digital e o pedido continuam pedindo `sale_price`,
    # `promotional_price` e `current_price`. O que mudou é de onde a resposta
    # vem — antes de uma coluna, agora de um cálculo que olha as tabelas de
    # desconto válidas NESTE instante.
    # ------------------------------------------------------------------

    @property
    def sale_price(self):
        """O preço cheio cadastrado. É referência, e só muda quando editado."""
        return self.base_price

    # OS SETTERS EXISTEM PARA O NOME ANTIGO CONTINUAR GRAVANDO.
    #
    # `Product(sale_price=10)` e `produto.sale_price = 10` seguem funcionando: o
    # Django aceita propriedade com setter nos kwargs do construtor. Sem isto, a
    # renomeação das colunas obrigaria a reescrever cinquenta chamadas em
    # semeadura, testes e desserialização do sync — cada uma delas uma chance
    # de deixar um preço zerado para trás.
    @sale_price.setter
    def sale_price(self, valor):
        self.base_price = valor

    @property
    def promotional_price(self):
        """O promocional em vigor: da promoção ativa, ou o do cadastro.

        Devolve `None` quando não há promocional nenhum — é o que
        `current_price` espera para cair no preço cheio, e era o que a coluna
        anulável dizia antes.
        """
        oferta = self.active_promotion
        if oferta is not None:
            return oferta.price
        manual = self.base_promotional_price
        if manual is not None and manual > 0:
            return manual
        return None

    @promotional_price.setter
    def promotional_price(self, valor):
        self.base_promotional_price = valor

    @property
    def current_price(self):
        """O que o cliente paga. É por aqui que TODO preço de venda passa."""
        promocional = self.promotional_price
        return promocional if promocional is not None else self.base_price

    @property
    def active_promotion(self):
        """A promoção que venceu a disputa por este produto, se houver.

        A resposta pode vir pendurada pelo serializer da listagem
        (`primar`): sem isso, desenhar uma grade de trinta produtos custaria
        trinta vezes a mesma consulta.
        """
        from apps.promotions.pricing import oferta_para

        return oferta_para(self)

    @property
    def compare_at_price(self):
        """O valor riscado, o "de". `None` quando não há nada a riscar.

        A promoção pode ditar um "de" MAIOR que o cadastrado ("de 30 por 15"
        num produto de 20) — é assim que encarte se escreve, e por isso o
        número vem dela quando ela o informa.
        """
        oferta = self.active_promotion
        if oferta is not None:
            return oferta.compare_at if oferta.compare_at > oferta.price else None
        manual = self.base_promotional_price
        if manual is not None and 0 < manual < self.base_price:
            return self.base_price
        return None
