prompt = f"""You are a strict binary HTML classifier.

Classify the WHOLE provided HTML chunk.

Return true ONLY if the whole HTML chunk is exactly one standalone, complete, actionable individual flight ticket card.
hint: you dont know the updated list of airiline names, so just based on its positoion and format find out that card
contains airline name or not.

A true result must contain:
- one specific airline
- route/origin and destination
- flight time or departure/arrival time
- price
- selectable/actionable CTA

Return false if ANY of these apply:
- The chunk contains a valid flight card but one of its chileds contain full valid flight card either.
- The chunk contains a banner, marketing image, advertisement, hotel promotion, header, footer, filter, summary, sticky bar, or non-card content outside the card.
- The chunk contains multiple flight cards.
- The chunk is a list/wrapper/container of cards.
- The chunk is only a partial component of a card.
- Airline, route, time, or price is missing or unclear.

Responsive mobile/desktop duplicate elements inside the same card do not count as multiple cards.

Return ONLY valid JSON.
- why should be complete but very very small.
Schema:
{{"is_ticket": <boolean>, "confidence": <number_between_0_and_1>, "why": false because its ticket + banner}}

HTML:
\"\"\"{html_chunk[:MAX_HTML_CHARS]}\"\"\"
"""








if __name__ == "__main__":
    if not start_ollama_server():
        raise RuntimeError("Could not start Ollama server.")

    with open("/kaggle/input/datasets/rezapourmoridi/flight-ticket-html/real_dataset_snap_not_tested.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    correct_count = 0
    print(f"{'ID':<25} | {'Expected':<10} | {'Predicted':<10} | {'Confidence':<10} | {'Status'}")
    print("-" * 80)

    for item in dataset:
        is_valid, confidence = final_validation(item["html"])
        expected = item["is_flight_card"]
        passed = (is_valid == expected)

        if passed:
            correct_count += 1

        print(
            f"{item['id']:<25} | {str(expected):<10} | {str(is_valid):<10} | "
            f"{confidence:<10.2f} | {'✅' if passed else '❌'}"
        )

    print("-" * 80)
    print(f"Total: {len(dataset)} | Accuracy: {correct_count / len(dataset):.1%}")