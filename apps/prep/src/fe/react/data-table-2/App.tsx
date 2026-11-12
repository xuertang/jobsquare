import { useState } from "react";

const users = [
  {
    id: 1,
    name: "Emily Chen",
    age: 28,
    occupation: "Software Engineer",
  },
  {
    id: 2,
    name: "Ryan Thompson",
    age: 32,
    occupation: "Marketing Manager",
  },
  {
    id: 3,
    name: "Sophia Patel",
    age: 25,
    occupation: "Data Analyst",
  },
  {
    id: 4,
    name: "Michael Lee",
    age: 41,
    occupation: "CEO",
  },
  {
    id: 5,
    name: "Olivia Brown",
    age: 29,
    occupation: "Graphic Designer",
  },
  {
    id: 6,
    name: "Alexander Hall",
    age: 38,
    occupation: "Sales Representative",
  },
  {
    id: 7,
    name: "Isabella Davis",
    age: 26,
    occupation: "Teacher",
  },
  {
    id: 8,
    name: "Ethan White",
    age: 35,
    occupation: "Lawyer",
  },
  {
    id: 9,
    name: "Lily Tran",
    age: 30,
    occupation: "Nurse",
  },
  {
    id: 10,
    name: "Julian Sanchez",
    age: 39,
    occupation: "Engineer",
  },
  {
    id: 11,
    name: "Ava Martin",
    age: 27,
    occupation: "Journalist",
  },
  {
    id: 12,
    name: "Benjamin Walker",
    age: 42,
    occupation: "Doctor",
  },
  {
    id: 13,
    name: "Charlotte Brooks",
    age: 31,
    occupation: "HR Manager",
  },
  {
    id: 14,
    name: "Gabriel Harris",
    age: 36,
    occupation: "IT Consultant",
  },
  {
    id: 15,
    name: "Hannah Taylor",
    age: 24,
    occupation: "Student",
  },
  {
    id: 16,
    name: "Jackson Brown",
    age: 40,
    occupation: "Business Owner",
  },
  {
    id: 17,
    name: "Kayla Lewis",
    age: 33,
    occupation: "Event Planner",
  },
  {
    id: 18,
    name: "Logan Mitchell",
    age: 37,
    occupation: "Architect",
  },
  {
    id: 19,
    name: "Mia Garcia",
    age: 29,
    occupation: "Artist",
  },
  {
    id: 20,
    name: "Natalie Hall",
    age: 34,
    occupation: "Teacher",
  },
  {
    id: 21,
    name: "Oliver Patel",
    age: 38,
    occupation: "Software Developer",
  },
  {
    id: 22,
    name: "Penelope Martin",
    age: 26,
    occupation: "Writer",
  },
  {
    id: 23,
    name: "Quinn Lee",
    age: 35,
    occupation: "Entrepreneur",
  },
  {
    id: 24,
    name: "Rachel Kim",
    age: 30,
    occupation: "Dentist",
  },
  {
    id: 25,
    name: "Samuel Jackson",
    age: 42,
    occupation: "Lawyer",
  },
  {
    id: 26,
    name: "Tessa Hall",
    age: 28,
    occupation: "Graphic Designer",
  },
  {
    id: 27,
    name: "Uma Patel",
    age: 39,
    occupation: "Marketing Manager",
  },
  {
    id: 28,
    name: "Vincent Brooks",
    age: 36,
    occupation: "IT Consultant",
  },
  {
    id: 29,
    name: "Walter White",
    age: 41,
    occupation: "Engineer",
  },
  {
    id: 30,
    name: "Xavier Sanchez",
    age: 33,
    occupation: "Sales Representative",
  },
  {
    id: 31,
    name: "Yvonne Martin",
    age: 29,
    occupation: "Teacher",
  },
  {
    id: 32,
    name: "Zoe Lee",
    age: 27,
    occupation: "Data Analyst",
  },
  {
    id: 33,
    name: "Abigail Brown",
    age: 34,
    occupation: "Nurse",
  },
  {
    id: 34,
    name: "Caleb Harris",
    age: 38,
    occupation: "Business Owner",
  },
  {
    id: 35,
    name: "Diana Taylor",
    age: 31,
    occupation: "Event Planner",
  },
  {
    id: 36,
    name: "Eleanor Walker",
    age: 40,
    occupation: "CEO",
  },
];
type User = (typeof users)[number];
type SortField = "id" | "name" | "age" | "occupation";
type SortDirection = "asc" | "desc";

const paginateUsers = (
  usersList: Array<User>,
  page: number,
  pageSize: number,
) => {
  const start = (page - 1) * pageSize;
  const end = start + pageSize;

  const pageUsers = usersList.slice(start, end);
  const totalPages = Math.ceil(usersList.length / pageSize);
  return { pageUsers, totalPages };
};

const sortUsers = (
  usersList: Array<User>,
  field: SortField | null,
  direction: SortDirection,
) => {
  const usersClone = usersList.slice();

  switch (field) {
    case "id":
    case "age": {
      return usersClone.sort((a, b) =>
        direction === "asc" ? a[field] - b[field] : b[field] - a[field],
      );
    }
    case "name":
    case "occupation": {
      return usersClone.sort((a, b) =>
        direction === "asc"
          ? a[field].localeCompare(b[field])
          : b[field].localeCompare(a[field]),
      );
    }
    default: {
      return usersClone;
    }
  }
};
const columns = [
  { label: "ID", key: "id" },
  { label: "Name", key: "name" },
  { label: "Age", key: "age" },
  { label: "Occupation", key: "occupation" },
] as const;

export default function App() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);

  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedUsers = sortUsers(users, sortField, sortDirection);
  const { totalPages, pageUsers } = paginateUsers(sortedUsers, page, pageSize);

  return (
    <main>
      <h1>Data Table</h1>
      <table>
        <thead>
          <tr>
            {columns.map(({ label, key }) => (
              <th key={key}>
                <button
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                  }}
                  onClick={() => {
                    if (sortField != key) {
                      setSortField(key);
                      setSortDirection("asc");
                    } else {
                      setSortDirection(
                        sortDirection === "asc" ? "desc" : "asc",
                      );
                    }
                    setPage(1);
                  }}
                >
                  {label}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pageUsers.map(({ id, name, age, occupation }) => (
            <tr key={id}>
              <td>{id}</td>
              <td>{name}</td>
              <td>{age}</td>
              <td>{occupation}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <hr />
      <div style={{ display: "flex", gap: "32px" }}>
        <select
          aria-label="page size"
          onChange={(e) => {
            setPageSize(Number(e.target.value));
            setPage(1);
          }}
        >
          {[5, 10, 20].map((size) => (
            <option key={size}>{size}</option>
          ))}
        </select>

        <div style={{ display: "flex", gap: "8px" }}>
          <button disabled={page === 1} onClick={() => setPage(page - 1)}>
            Prev
          </button>
          <span aria-label="page number">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page === totalPages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </main>
  );
}
