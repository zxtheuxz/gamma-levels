# Níveis Derivados da Cadeia de Opções

Este documento descreve cálculos usados para transformar uma cadeia de opções em níveis de preço, zonas de suporte, resistência, atração, aceleração e mudança de regime.

O objetivo não é recalcular as gregas básicas exibidas pela plataforma, mas usar os dados da cadeia para construir métricas como:

- Gamma Exposure por strike
- Gamma Levels
- Zero Gamma ou Gamma Flip
- Call Wall
- Put Wall
- Gamma Magnet
- Gamma Cluster
- Delta Exposure por strike
- Vanna Levels
- Charm Levels
- Max Pain
- Expected Move
- níveis por concentração de open interest

## Implementação

A implementação Python deste documento está no pacote `gamma_levels/`. Consulte
`README.md` para o esquema de entrada e os parâmetros. Exemplo:

```powershell
python -m gamma_levels exemplo_cadeia.csv --valuation-date 2026-07-27 --rate 0.15
```

---

## 1. Dados necessários

Para cada opção da cadeia:

```text
tipo: call ou put
strike
vencimento
open_interest
volume
delta
gamma
vega
vanna
charm
preco_do_ativo
multiplicador_do_contrato
```

Também é importante conhecer:

```text
preço atual do ativo
dias até o vencimento
taxa de juros
volatilidade implícita
quantidade do ativo representada por contrato
```

As gregas podem vir diretamente da plataforma ou ser calculadas externamente.

---

# 2. Gamma Exposure por opção

O Gamma Exposure estima quanto o delta agregado pode mudar quando o preço do ativo se movimenta.

Para uma opção individual:

\[
GEX_i =
\Gamma_i
\times
OI_i
\times
Q
\times
S^2
\times
0{,}01
\]

Onde:

- \(\Gamma_i\): gamma da opção
- \(OI_i\): open interest
- \(Q\): quantidade do ativo por contrato
- \(S\): preço atual do ativo
- \(0{,}01\): movimento de 1% no ativo

O resultado representa a variação aproximada da exposição delta para um movimento de 1% no ativo.

---

# 3. Convenção de sinal do GEX

O gamma matemático de uma opção comprada é positivo. Porém, para estimar o posicionamento dos dealers, é necessário assumir quem está comprado e quem está vendido.

Uma convenção simplificada muito usada é:

\[
GEX_{\text{calls}} > 0
\]

\[
GEX_{\text{puts}} < 0
\]

Assim:

\[
GEX_i =
\begin{cases}
+\Gamma_i \times OI_i \times Q \times S^2 \times 0{,}01,
& \text{call} \\
-\Gamma_i \times OI_i \times Q \times S^2 \times 0{,}01,
& \text{put}
\end{cases}
\]

Essa convenção é apenas uma estimativa. O open interest não mostra diretamente se o dealer está comprado ou vendido.

Uma implementação mais avançada pode ajustar o sinal usando:

- agressão da negociação;
- preço da negociação em relação ao bid e ask;
- variação do open interest;
- fluxo histórico;
- classificação de abertura ou fechamento.

---

# 4. GEX total

O GEX total da cadeia é:

\[
GEX_{\text{total}} =
\sum_{i=1}^{n} GEX_i
\]

Interpretação geral:

## GEX total positivo

Pode indicar que o hedge tende a atuar contra o movimento:

- venda do ativo quando sobe;
- compra do ativo quando cai;
- maior possibilidade de estabilização;
- menor expansão de volatilidade;
- maior chance de retorno para níveis de concentração.

## GEX total negativo

Pode indicar que o hedge tende a acompanhar o movimento:

- compra do ativo quando sobe;
- venda do ativo quando cai;
- maior possibilidade de aceleração;
- maior expansão de volatilidade;
- rompimentos potencialmente mais fortes.

Essa interpretação depende da hipótese de posicionamento adotada.

---

# 5. GEX por strike

O GEX deve ser agrupado por strike:

\[
GEX(K) =
\sum_{i:\ strike_i=K} GEX_i
\]

Exemplo de tabela:

```text
strike | gex_calls | gex_puts | gex_liquido
30,00  |  120000   | -350000  | -230000
31,00  |  180000   | -160000  |   20000
32,00  |  450000   |  -90000  |  360000
33,00  |  800000   |  -50000  |  750000
```

Esse agrupamento cria o mapa principal dos Gamma Levels.

---

# 6. Gamma Levels

Gamma Levels são strikes com concentrações relevantes de gamma exposure.

Um Gamma Level pode ser definido por:

\[
|GEX(K)| \geq \text{limite}
\]

O limite pode ser calculado por percentil:

\[
GammaLevel =
|GEX(K)| \geq P_{90}(|GEX|)
\]

Ou seja, considerar Gamma Levels os strikes cujo GEX absoluto esteja entre os 10% maiores da cadeia.

Outra opção é usar média e desvio padrão:

\[
GammaLevel =
|GEX(K)|
>
\mu_{|GEX|}
+
2\sigma_{|GEX|}
\]

Os níveis podem ser classificados como:

```text
Gamma positivo elevado
Gamma negativo elevado
Gamma neutro
```

---

# 7. Gamma Level positivo

Um strike com GEX positivo elevado pode funcionar como:

- região de estabilização;
- região de absorção;
- nível de atração;
- suporte ou resistência, dependendo da posição do preço;
- área em que o hedge tende a reduzir o movimento.

Se o preço estiver acima do strike, ele pode atuar como suporte.

Se o preço estiver abaixo do strike, ele pode atuar como resistência.

Isso não é garantido. A interpretação depende do vencimento, distância do preço e fluxo do dia.

---

# 8. Gamma Level negativo

Um strike com GEX negativo elevado pode indicar uma região de maior instabilidade.

Próximo desse nível, o hedge estimado pode:

- amplificar rompimentos;
- aumentar a velocidade do movimento;
- elevar a volatilidade;
- reduzir a capacidade de contenção do preço.

Um nível de gamma negativo não deve ser tratado automaticamente como suporte ou resistência.

Ele pode ser melhor interpretado como uma região de aceleração potencial.

---

# 9. Gamma Cluster

Gamma Cluster é uma faixa com vários strikes próximos apresentando GEX relevante.

Para calcular:

1. Ordenar os strikes.
2. Identificar strikes consecutivos com GEX acima de um limite.
3. Agrupar os strikes dentro de uma distância máxima.
4. Somar o GEX da faixa.

\[
GEX_{\text{cluster}} =
\sum_{K=a}^{b} GEX(K)
\]

O centro ponderado do cluster é:

\[
K_{\text{cluster}} =
\frac{
\sum_K K \times |GEX(K)|
}{
\sum_K |GEX(K)|
}
\]

Esse valor pode ser usado como centro da zona.

A largura da zona pode ser definida pelos strikes extremos do grupo:

\[
Zona_{\text{cluster}} = [K_{\min}, K_{\max}]
\]

---

# 10. Gamma Magnet

Gamma Magnet é um strike ou região que pode atrair o preço devido à concentração de gamma e open interest.

Uma forma simples:

\[
GammaMagnet =
\arg\max_K |GEX(K)|
\]

Uma forma ponderada pela distância do preço:

\[
MagnetScore(K) =
\frac{
|GEX(K)|
}{
1 + |S-K|
}
\]

O Gamma Magnet será:

\[
GammaMagnet =
\arg\max_K MagnetScore(K)
\]

Pode-se usar distância percentual:

\[
Dist(K) =
\frac{|S-K|}{S}
\]

\[
MagnetScore(K) =
\frac{
|GEX(K)|
}{
1 + Dist(K)
}
\]

Assim, níveis muito distantes recebem menos peso.

---

# 11. Gamma Flip ou Zero Gamma

O Gamma Flip é o preço do ativo em que o GEX agregado muda de sinal.

Não basta observar o GEX calculado no preço atual.

É necessário recalcular o gamma de todas as opções em vários preços simulados.

Para cada preço simulado \(S_j\):

\[
GEX_{\text{total}}(S_j)
=
\sum_i
GEX_i(S_j)
\]

Depois, localizar dois preços consecutivos:

\[
GEX_{\text{total}}(S_1) < 0
\]

\[
GEX_{\text{total}}(S_2) > 0
\]

O Zero Gamma pode ser aproximado por interpolação:

\[
S_{\text{flip}}
=
S_1
+
\frac{
-GEX(S_1)
}{
GEX(S_2)-GEX(S_1)
}
(S_2-S_1)
\]

Interpretação:

```text
Acima do Gamma Flip:
regime potencialmente mais estável, dependendo da convenção usada.

Abaixo do Gamma Flip:
regime potencialmente mais instável e direcional.
```

A interpretação deve ser validada com a convenção de sinal escolhida.

---

# 12. Gamma Flip por vencimento

Além do Gamma Flip da cadeia inteira, é útil calcular por vencimento:

\[
GEX_{\text{total},T}(S)
=
\sum_{i:\ vencimento_i=T} GEX_i(S)
\]

Assim é possível obter:

```text
Gamma Flip do vencimento curto
Gamma Flip do vencimento mensal
Gamma Flip da cadeia completa
```

O vencimento curto geralmente reage mais rapidamente, enquanto vencimentos longos podem criar níveis mais persistentes.

---

# 13. Call Wall

Call Wall é uma concentração relevante em calls.

Definição por open interest:

\[
CallWall_{OI}
=
\arg\max_K OI_{\text{calls}}(K)
\]

Definição por gamma exposure:

\[
CallWall_{GEX}
=
\arg\max_K GEX_{\text{calls}}(K)
\]

Definição combinada:

\[
CallWallScore(K)
=
OI_{\text{calls}}(K)
\times
\Gamma_{\text{calls}}(K)
\]

Ou:

\[
CallWallScore(K)
=
GEX_{\text{calls}}(K)
\times
\left(1+\frac{Volume_{\text{calls}}(K)}{OI_{\text{calls}}(K)}\right)
\]

O strike com maior score é o Call Wall.

Possível interpretação:

- resistência;
- região de travamento;
- zona de defesa;
- nível de atração próximo do vencimento.

---

# 14. Put Wall

Put Wall é uma concentração relevante em puts.

Definição por open interest:

\[
PutWall_{OI}
=
\arg\max_K OI_{\text{puts}}(K)
\]

Definição por gamma:

\[
PutWall_{GEX}
=
\arg\max_K |GEX_{\text{puts}}(K)|
\]

Definição combinada:

\[
PutWallScore(K)
=
OI_{\text{puts}}(K)
\times
\Gamma_{\text{puts}}(K)
\]

Ou:

\[
PutWallScore(K)
=
|GEX_{\text{puts}}(K)|
\times
\left(1+\frac{Volume_{\text{puts}}(K)}{OI_{\text{puts}}(K)}\right)
\]

Possível interpretação:

- suporte;
- região de defesa;
- zona de concentração;
- nível de atração próximo ao vencimento.

---

# 15. Call Resistance Level

Pode-se calcular uma resistência agregada usando os principais strikes de call acima do preço.

Selecionar apenas:

\[
K > S
\]

Depois calcular:

\[
ResistanceScore(K)
=
|GEX_{\text{calls}}(K)|
\times
\left(1+\frac{Volume_{\text{calls}}(K)}{OI_{\text{calls}}(K)}\right)
\times
DistanceWeight(K)
\]

Com:

\[
DistanceWeight(K)
=
e^{-\lambda |K-S|/S}
\]

O nível de resistência é:

\[
ResistanceLevel =
\arg\max_{K>S} ResistanceScore(K)
\]

O GEX já contém open interest. Multiplicá-lo novamente por OI daria peso
quadrático ao número de contratos e, por isso, não é usado na implementação.

---

# 16. Put Support Level

Selecionar apenas puts abaixo do preço:

\[
K < S
\]

Calcular:

\[
SupportScore(K)
=
|GEX_{\text{puts}}(K)|
\times
\left(1+\frac{Volume_{\text{puts}}(K)}{OI_{\text{puts}}(K)}\right)
\times
DistanceWeight(K)
\]

Com:

\[
DistanceWeight(K)
=
e^{-\lambda |K-S|/S}
\]

O nível de suporte é:

\[
SupportLevel =
\arg\max_{K<S} SupportScore(K)
\]

---

# 17. Delta Exposure por strike

O Delta Exposure mostra a exposição direcional agregada.

Para cada opção:

\[
DEX_i =
\Delta_i
\times
OI_i
\times
Q
\times
S
\]

Agrupamento por strike:

\[
DEX(K) =
\sum_{i:\ strike_i=K} DEX_i
\]

Uma convenção simplificada:

```text
call: delta positivo
put: delta negativo
```

Para estimar dealers, o sinal pode ser invertido.

Níveis com DEX elevado podem indicar regiões onde uma pequena mudança de preço produz grande alteração na necessidade de hedge.

---

# 18. Delta Wall

Delta Wall é o strike com maior exposição delta absoluta:

\[
DeltaWall =
\arg\max_K |DEX(K)|
\]

Também pode ser separado:

\[
CallDeltaWall =
\arg\max_K DEX_{\text{calls}}(K)
\]

\[
PutDeltaWall =
\arg\max_K |DEX_{\text{puts}}(K)|
\]

Esses níveis podem complementar Call Wall e Put Wall.

---

# 19. Vanna Exposure por strike

Vanna mede a mudança do delta em função da volatilidade implícita.

Para cada opção:

\[
VannaExposure_i =
Vanna_i
\times
OI_i
\times
Q
\]

Para uma variação de 1 ponto percentual na volatilidade:

\[
VannaExposure_{1\%,i}
=
Vanna_i
\times
OI_i
\times
Q
\times
0{,}01
\]

Essa fórmula pressupõe que vanna seja fornecida por (1{,}00) de volatilidade.
Se a fonte a expressar por 1 ponto percentual, a unidade deve ser convertida.

Agrupamento:

\[
VannaExposure(K)
=
\sum_{i:\ strike_i=K} VannaExposure_i
\]

Strikes com elevada Vanna Exposure podem se tornar relevantes quando a volatilidade implícita sobe ou cai rapidamente.

---

# 20. Vanna Level

O Vanna Level pode ser definido como:

\[
VannaLevel =
\arg\max_K |VannaExposure(K)|
\]

Também pode ser criado um conjunto de níveis:

\[
|VannaExposure(K)|
\geq
P_{90}(|VannaExposure|)
\]

Esses níveis podem ganhar importância durante:

- queda rápida da volatilidade;
- aumento brusco da volatilidade;
- eventos;
- divulgação de resultados;
- proximidade do vencimento.

---

# 21. Charm Exposure por strike

Charm mede a mudança do delta pela passagem do tempo.

\[
CharmExposure_i =
Charm_i
\times
OI_i
\times
Q
\]

Para um dia:

\[
CharmExposure_{\text{dia},i}
=
Charm_i
\times
OI_i
\times
Q
\times
\frac{1}{252}
\]

Essa conversão pressupõe charm anual. Se a fonte já fornecer charm por dia, não se
deve dividir novamente por 252.

Agrupamento:

\[
CharmExposure(K)
=
\sum_{i:\ strike_i=K} CharmExposure_i
\]

---

# 22. Charm Level

O Charm Level é o strike com maior exposição charm absoluta:

\[
CharmLevel =
\arg\max_K |CharmExposure(K)|
\]

Esses níveis podem ser mais relevantes:

- perto do vencimento;
- na abertura do pregão;
- após finais de semana;
- após feriados;
- quando opções próximas do dinheiro concentram open interest.

---

# 23. Combined Dealer Exposure Level

Pode-se combinar gamma, delta, vanna e charm por strike.

Primeiro, normalizar cada métrica:

\[
Z_{GEX}(K)
=
\frac{
GEX(K)-\mu_{GEX}
}{
\sigma_{GEX}
}
\]

\[
Z_{DEX}(K)
=
\frac{
DEX(K)-\mu_{DEX}
}{
\sigma_{DEX}
}
\]

\[
Z_{Vanna}(K)
=
\frac{
Vanna(K)-\mu_{Vanna}
}{
\sigma_{Vanna}
}
\]

\[
Z_{Charm}(K)
=
\frac{
Charm(K)-\mu_{Charm}
}{
\sigma_{Charm}
}
\]

Depois:

\[
DealerExposure(K)
=
w_g Z_{GEX}(K)
+
w_d Z_{DEX}(K)
+
w_v Z_{Vanna}(K)
+
w_c Z_{Charm}(K)
\]

Onde:

\[
w_g+w_d+w_v+w_c=1
\]

Esse cálculo cria um mapa único de exposição por strike.

---

# 24. Open Interest Wall

Pode-se calcular níveis apenas pela concentração de open interest.

## Call OI Wall

\[
CallOIWall =
\arg\max_K OI_{\text{calls}}(K)
\]

## Put OI Wall

\[
PutOIWall =
\arg\max_K OI_{\text{puts}}(K)
\]

## OI líquido por strike

\[
OI_{\text{líquido}}(K)
=
OI_{\text{calls}}(K)
-
OI_{\text{puts}}(K)
\]

## OI total por strike

\[
OI_{\text{total}}(K)
=
OI_{\text{calls}}(K)
+
OI_{\text{puts}}(K)
\]

O maior OI total pode ser tratado como um nível de concentração, mas não revela direção sozinho.

---

# 25. Open Interest Change Level

A mudança do open interest pode mostrar criação ou desmontagem de níveis.

\[
\Delta OI(K)
=
OI_{\text{atual}}(K)
-
OI_{\text{anterior}}(K)
\]

Nível de maior criação:

\[
NewPositionLevel =
\arg\max_K \Delta OI(K)
\]

Nível de maior desmontagem:

\[
UnwindLevel =
\arg\min_K \Delta OI(K)
\]

É útil calcular separadamente para calls e puts.

---

# 26. Volume-to-OI Level

A relação volume/open interest ajuda a destacar strikes com atividade nova.

\[
VOIRatio(K)
=
\frac{
Volume(K)
}{
OI(K)
}
\]

Strikes com:

```text
volume elevado
open interest elevado
aumento de open interest
```

podem representar criação relevante de novas posições.

O nível pode ser:

\[
VolumeOILevel =
\arg\max_K VOIRatio(K)
\]

Esse cálculo deve ignorar strikes com open interest muito pequeno, pois a razão pode ficar artificialmente alta.

---

# 27. Max Pain

Para cada preço de liquidação simulado \(S_j\):

## Valor das calls

\[
Pain_{\text{calls}}(S_j)
=
\sum_K
\max(S_j-K,0)
\times
OI_{\text{calls}}(K)
\times
Q
\]

## Valor das puts

\[
Pain_{\text{puts}}(S_j)
=
\sum_K
\max(K-S_j,0)
\times
OI_{\text{puts}}(K)
\times
Q
\]

## Valor total

\[
Pain_{\text{total}}(S_j)
=
Pain_{\text{calls}}(S_j)
+
Pain_{\text{puts}}(S_j)
\]

O Max Pain é:

\[
MaxPain =
\arg\min_{S_j} Pain_{\text{total}}(S_j)
\]

Pode funcionar como nível de referência perto do vencimento, mas não deve ser tratado como destino obrigatório do preço.

---

# 28. Expected Move

O movimento esperado pode ser calculado pela volatilidade implícita:

\[
ExpectedMove =
S
\times
IV
\times
\sqrt{T}
\]

Nível superior:

\[
UpperExpectedMove =
S + ExpectedMove
\]

Nível inferior:

\[
LowerExpectedMove =
S - ExpectedMove
\]

Esses dois preços formam uma faixa implícita.

---

# 29. Expected Move pelo straddle ATM

Usando call e put no strike mais próximo do preço:

\[
ExpectedMove_{\text{straddle}}
=
PreçoCall_{ATM}
+
PreçoPut_{ATM}
\]

Faixa:

\[
UpperLevel =
S + ExpectedMove_{\text{straddle}}
\]

\[
LowerLevel =
S - ExpectedMove_{\text{straddle}}
\]

Também pode ser usada uma fração do straddle, dependendo da metodologia:

\[
ExpectedMove =
0{,}85
\times
Straddle_{ATM}
\]

O fator deve ser validado historicamente.

---

# 30. Implied Range por desvio padrão

Usando volatilidade implícita:

## Um desvio padrão

\[
Range_{1\sigma}
=
S
\pm
S \times IV \times \sqrt{T}
\]

## Meio desvio padrão

\[
Range_{0{,}5\sigma}
=
S
\pm
0{,}5
\times
S
\times
IV
\times
\sqrt{T}
\]

## Dois desvios padrão

\[
Range_{2\sigma}
=
S
\pm
2
\times
S
\times
IV
\times
\sqrt{T}
\]

Esses níveis podem ser plotados no gráfico como bandas.

---

# 31. Volatility Trigger

Volatility Trigger é um nível que separa dois regimes de comportamento esperado da volatilidade.

Uma definição prática pode ser o próprio Gamma Flip:

\[
VolatilityTrigger = GammaFlip
\]

Outra abordagem é encontrar o preço onde o GEX negativo atinge determinado limite:

\[
GEX_{\text{total}}(S)
<
-GEX_{\text{limite}}
\]

O primeiro preço que atende à condição pode ser tratado como Volatility Trigger.

Não existe uma fórmula universal. A metodologia deve ser definida e testada.

---

# 32. Gamma Imbalance

O desequilíbrio de gamma pode ser calculado por:

\[
GammaImbalance =
\frac{
GEX_{\text{calls}} - |GEX_{\text{puts}}|
}{
|GEX_{\text{calls}}| + |GEX_{\text{puts}}|
}
\]

O resultado fica aproximadamente entre \(-1\) e \(+1\).

```text
próximo de +1:
domínio das calls na convenção usada

próximo de -1:
domínio das puts na convenção usada

próximo de 0:
equilíbrio
```

Também pode ser calculado por strike.

---

# 33. Put/Call Gamma Ratio

\[
PCR_{\Gamma}
=
\frac{
|GEX_{\text{puts}}|
}{
|GEX_{\text{calls}}|
}
\]

Pode ser calculado:

```text
na cadeia inteira
por vencimento
por strike
somente perto do dinheiro
```

Um valor elevado mostra maior concentração relativa de gamma nas puts.

---

# 34. Gamma Concentration Ratio

Esse cálculo mostra quanto do gamma está concentrado nos principais strikes.

\[
GammaConcentration_N =
\frac{
\sum_{j=1}^{N} |GEX(K_j)|
}{
\sum_K |GEX(K)|
}
\]

Onde \(K_j\) são os \(N\) strikes com maior GEX absoluto.

Exemplo:

```text
GammaConcentration_3 = 0,65
```

Isso significa que 65% do gamma absoluto está concentrado nos três principais strikes.

Quanto maior a concentração, mais importantes tendem a ser esses níveis.

---

# 35. Gamma Center of Mass

O centro de massa do gamma é:

\[
GammaCenter =
\frac{
\sum_K K \times |GEX(K)|
}{
\sum_K |GEX(K)|
}
\]

Pode ser calculado separadamente:

\[
CallGammaCenter =
\frac{
\sum_K K \times |GEX_{\text{calls}}(K)|
}{
\sum_K |GEX_{\text{calls}}(K)|
}
\]

\[
PutGammaCenter =
\frac{
\sum_K K \times |GEX_{\text{puts}}(K)|
}{
\sum_K |GEX_{\text{puts}}(K)|
}
\]

Esses valores representam o preço médio ponderado das principais exposições.

---

# 36. Distance to Gamma Level

Para cada nível:

\[
Distance(K)
=
\frac{
K-S
}{
S
}
\times 100
\]

Assim é possível ordenar:

```text
suporte gamma mais próximo
resistência gamma mais próxima
call wall mais próximo
put wall mais próximo
zero gamma
```

Também pode ser calculada a distância em volatilidade:

\[
Distance_{\sigma}(K)
=
\frac{
K-S
}{
S \times IV \times \sqrt{T}
}
\]

Isso mostra quantos desvios implícitos o nível está distante do preço.

---

# 37. Decaimento de relevância por vencimento

Exposições de vencimentos diferentes podem receber pesos.

Exemplo de peso exponencial:

\[
Weight(T)
=
e^{-\lambda T}
\]

GEX ajustado:

\[
GEX_{\text{ajustado},i}
=
GEX_i
\times
Weight(T_i)
\]

Assim, vencimentos próximos recebem maior peso.

Também é possível usar:

\[
Weight(T)
=
\frac{1}{\sqrt{T}}
\]

A escolha deve ser validada historicamente.

---

# 38. Decaimento por distância do strike

Strikes muito distantes podem receber menor peso:

\[
DistanceWeight(K)
=
e^{-\lambda |K-S|/S}
\]

GEX ajustado:

\[
GEX_{\text{distance}}(K)
=
GEX(K)
\times
DistanceWeight(K)
\]

Isso evita que um grande open interest muito distante domine o mapa.

---

# 39. Nível composto de suporte

Um suporte derivado apenas de opções pode combinar:

\[
SupportComposite(K)
=
a \times |GEX_{\text{puts}}(K)|
+
b \times OI_{\text{puts}}(K)
+
c \times |DEX_{\text{puts}}(K)|
+
d \times |\Delta OI_{\text{puts}}(K)|
\]

Aplicar somente em:

\[
K < S
\]

O suporte principal será:

\[
SupportLevel =
\arg\max_{K<S} SupportComposite(K)
\]

Antes de combinar, as variáveis devem ser normalizadas.

---

# 40. Nível composto de resistência

\[
ResistanceComposite(K)
=
a \times GEX_{\text{calls}}(K)
+
b \times OI_{\text{calls}}(K)
+
c \times DEX_{\text{calls}}(K)
+
d \times |\Delta OI_{\text{calls}}(K)|
\]

Aplicar somente em:

\[
K > S
\]

A resistência principal será:

\[
ResistanceLevel =
\arg\max_{K>S} ResistanceComposite(K)
\]

---

# 41. Normalização das métricas

Para combinar GEX, DEX, OI e outras métricas, é necessário normalizar.

## Min-Max

\[
X_{\text{norm}} =
\frac{
X-X_{\min}
}{
X_{\max}-X_{\min}
}
\]

## Z-score

\[
Z_X =
\frac{
X-\mu_X
}{
\sigma_X
}
\]

## Normalização pelo total

\[
X_{\text{share}}(K)
=
\frac{
|X(K)|
}{
\sum_K |X(K)|
}
\]

A normalização pelo total costuma ser prática para exposições por strike.

---

# 42. Transformação de linha em zona

Um strike não precisa ser tratado como uma linha exata.

Pode-se criar uma zona usando:

\[
Zona(K) =
[K-\delta,\ K+\delta]
\]

O valor de \(\delta\) pode ser:

```text
metade da distância entre strikes
uma fração do ATR
uma fração do expected move
spread médio da ação
```

Usando expected move:

\[
\delta =
c
\times
S
\times
IV
\times
\sqrt{T}
\]

Assim, níveis passam a ser regiões de preço.

---

# 43. Atualização intradiária

Open interest normalmente não é atualizado em tempo real da mesma forma que preço e volume.

Durante o pregão, pode-se manter o OI fixo e recalcular:

```text
gamma
delta
GEX
DEX
Gamma Flip
distância dos níveis
expected move
```

Com o novo preço do ativo e nova volatilidade implícita.

No fechamento ou quando novos dados de OI forem disponibilizados, atualizar toda a cadeia.

---

# 44. Ordem recomendada de implementação

```text
1. Importar a cadeia.
2. Separar calls e puts.
3. Agrupar open interest por strike.
4. Calcular GEX por opção.
5. Agregar GEX por strike.
6. Calcular GEX total.
7. Identificar Gamma Levels.
8. Calcular Gamma Magnet.
9. Calcular Call Wall.
10. Calcular Put Wall.
11. Simular preços e encontrar Gamma Flip.
12. Calcular DEX por strike.
13. Calcular Vanna Exposure.
14. Calcular Charm Exposure.
15. Calcular Max Pain.
16. Calcular Expected Move.
17. Criar zonas em vez de linhas.
18. Recalcular intraday com preço e IV atualizados.
```

---

# 45. Saída sugerida

```text
preco_ativo
gex_total
gamma_flip
gamma_magnet
call_wall
put_wall
call_delta_wall
put_delta_wall
vanna_level
charm_level
max_pain
expected_move_superior
expected_move_inferior
support_level_1
support_level_2
resistance_level_1
resistance_level_2
```

Tabela por strike:

```text
strike
oi_call
oi_put
delta_call
delta_put
gamma_call
gamma_put
gex_call
gex_put
gex_liquido
dex_call
dex_put
vanna_exposure
charm_exposure
distance_percent
support_composite
resistance_composite
```

---

# 46. Principais cálculos para começar

Para uma primeira versão, os cálculos mais importantes são:

```text
GEX por opção
GEX por strike
GEX total
Gamma Levels
Gamma Magnet
Gamma Flip
Call Wall
Put Wall
DEX por strike
Max Pain
Expected Move
```

Depois podem ser adicionados:

```text
Vanna Levels
Charm Levels
Gamma Clusters
Gamma Center of Mass
Gamma Concentration
Support Composite
Resistance Composite
```

---

# 47. Cuidados

- Não existe uma convenção universal de sinal para GEX.
- Open interest não identifica sozinho o lado do dealer.
- Call Wall e Put Wall não são fórmulas oficiais.
- Max Pain não garante convergência do preço.
- Um grande GEX distante do preço pode ter pouca relevância intradiária.
- Vencimentos próximos e distantes não devem receber automaticamente o mesmo peso.
- Opções ilíquidas podem distorcer volatilidade implícita e gregas.
- Dividendos e exercício antecipado podem alterar os cálculos.
- Os níveis devem ser validados historicamente no ativo e no vencimento analisado.
