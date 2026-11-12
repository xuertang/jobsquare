import { useRef, useState } from "react";
import "./styles.css";

const emojis = [
  "🐵",
  "🐶",
  "🦊",
  "🐱",
  "🦁",
  "🐯",
  "🐴",
  "🦄",
  "🦓",
  "🦌",
  "🐮",
  "🐷",
  "🐭",
  "🐹",
  "🐻",
  "🐨",
  "🐼",
  "🐽",
  "🐸",
  "🐰",
  "🐙",
];

type Item = {
  id: string;
  label: string;
};

function shuffle(arr: any[]) {
  for (let i = 0; i < arr.length; i++) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

function generateCards(total: number, match: number) {
  const numGroups = total / match;
  const emojisList = emojis.slice(0, numGroups);

  const cards = [];
  for (let i = 0; i < numGroups; i++) {
    const emoji = emojisList[i];
    let cur = 0;
    while (cur < match) {
      cards.push(emoji);
      cur++;
    }
  }
  shuffle(cards);
  return cards;
}

function MemoryGame({ cols = 4, rows = 4, delay = 2000, matchCount = 2 }) {
  const total = cols * rows;
  const [cards, setCards] = useState(generateCards(total, matchCount));
  const [flipped, setFlipped] = useState<number[]>([]);
  const [matched, setMatched] = useState(new Set());
  const waitTimer = useRef<number | null>(null);

  const handleFlip = (index: number) => {
    let curFlipped = flipped;

    if (waitTimer.current != null) {
      clearTimeout(waitTimer.current);
      waitTimer.current = null;
      curFlipped = [];
    }

    const newFlipped = [...curFlipped, index];
    setFlipped(newFlipped);

    if (newFlipped.length < matchCount) {
      return;
    }

    const allFlippedAreSame = newFlipped.every(
      (index) => cards[newFlipped[0]] === cards[index]
    );

    if (allFlippedAreSame) {
      const newMatchedSet = new Set(matched);
      newMatchedSet.add(cards[newFlipped[0]]);
      setMatched(newMatchedSet);
      setFlipped([]);

      return;
    }

    const timer = setTimeout(() => {
      setFlipped([]);
      waitTimer.current = null;
    }, delay);

    waitTimer.current = timer;
  };

  return (
    <div className="app">
      <div
        className="grid"
        style={{
          gridTemplateRows: `repeat(${rows}, var(--size))`,
          gridTemplateColumns: `repeat(${cols}, var(--size))`,
        }}
      >
        {cards.map((card, index) => {
          const isFlipped = flipped.includes(index);
          const isMatched = matched.has(cards[index]);
          return (
            <button
              key={index}
              className={["card", matched.has(cards[index]) && "card--revealed"]
                .filter(Boolean)
                .join(" ")}
              onClick={() => handleFlip(index)}
            >
              {(isFlipped || isMatched) && card}
            </button>
          );
        })}
      </div>
    </div>
  );
}
export default function App() {
  return <MemoryGame />;
}
